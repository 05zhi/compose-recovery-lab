// Package config parses declarative configuration only. It never runs commands,
// resolves environment values or loads user-controlled schema references.
package config

import (
	"bytes"
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/santhosh-tekuri/jsonschema/v5"
	"go.yaml.in/yaml/v3"
)

//go:embed schema.json
var Schema []byte

type Config struct {
	SchemaVersion int    `json:"schema_version"`
	Name          string `json:"name"`
	Template      string `json:"template"`
	Backup        struct {
		Type    string            `json:"type"`
		Path    string            `json:"path"`
		Mapping map[string]string `json:"mapping"`
	} `json:"backup"`
	Runtime struct {
		ImagesFile string `json:"images_file"`
		WorkDir    string `json:"work_dir"`
		Timeout    string `json:"timeout"`
	} `json:"runtime"`
	Checks []struct {
		ID       string `json:"id"`
		Required bool   `json:"required"`
	} `json:"checks"`
	Report struct {
		Formats []string `json:"formats"`
	} `json:"report"`
	Hash string `json:"-"`
}

func Load(filename string) (Config, error) {
	var zero Config
	f, err := os.Open(filename)
	if err != nil {
		return zero, errors.New("cannot open configuration")
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() {
		return zero, errors.New("configuration must be a regular file")
	}
	data, err := io.ReadAll(io.LimitReader(f, 65537))
	if err != nil {
		return zero, errors.New("cannot read configuration")
	}
	return Parse(data, filepath.Dir(filename))
}
func Parse(data []byte, base string) (Config, error) {
	var c Config
	if len(data) > 65536 {
		return c, errors.New("configuration exceeds 64 KiB")
	}
	dec := yaml.NewDecoder(bytes.NewReader(data))
	var document yaml.Node
	if err := dec.Decode(&document); err != nil {
		return c, errors.New("invalid YAML syntax (values omitted)")
	}
	if err := dec.Decode(new(yaml.Node)); err != io.EOF {
		return c, errors.New("exactly one YAML document is required")
	}
	if len(document.Content) != 1 {
		return c, errors.New("configuration must be one object")
	}
	locations := map[string]*yaml.Node{}
	budget := 2048
	value, err := convert(document.Content[0], "", 0, &budget, locations)
	if err != nil {
		return c, err
	}
	compiler := jsonschema.NewCompiler()
	if err = compiler.AddResource("drill.json", bytes.NewReader(Schema)); err != nil {
		return c, err
	}
	schema, err := compiler.Compile("drill.json")
	if err != nil {
		return c, err
	}
	if err = schema.Validate(value); err != nil {
		var validation *jsonschema.ValidationError
		if errors.As(err, &validation) {
			for len(validation.Causes) > 0 {
				validation = validation.Causes[0]
			}
			node := locations[validation.InstanceLocation]
			if node == nil {
				node = document.Content[0]
			}
			return c, at(node, "unsupported field or schema constraint violation (see drill v1 schema)")
		}
		return c, errors.New("invalid configuration schema")
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return c, errors.New("configuration cannot be encoded")
	}
	if err = json.Unmarshal(encoded, &c); err != nil {
		return c, errors.New("invalid configuration types")
	}
	timeout, err := time.ParseDuration(c.Runtime.Timeout)
	if err != nil || timeout < time.Second || timeout > time.Hour {
		return c, at(locations["/runtime/timeout"], "timeout must be between 1s and 1h")
	}
	for _, p := range []*string{&c.Backup.Path, &c.Runtime.ImagesFile, &c.Runtime.WorkDir} {
		if strings.Contains(*p, ":") || strings.Contains(*p, "\\") {
			return c, errors.New("paths must be Linux filesystem paths, not URLs or Windows paths")
		}
		if !filepath.IsAbs(*p) {
			*p = filepath.Join(base, *p)
		}
		*p, err = filepath.Abs(*p)
		if err != nil {
			return c, errors.New("cannot resolve config-relative path")
		}
	}
	// Hash the declarative content, excluding generated runtime credentials and resolved paths.
	sum := sha256.Sum256(encoded)
	c.Hash = hex.EncodeToString(sum[:])
	return c, nil
}
func at(n *yaml.Node, message string) error {
	if n == nil {
		return errors.New(message)
	}
	return fmt.Errorf("line %d, column %d: %s", n.Line, n.Column, message)
}
func convert(n *yaml.Node, pointer string, depth int, budget *int, locations map[string]*yaml.Node) (any, error) {
	*budget--
	if depth > 16 || *budget < 0 {
		return nil, at(n, "YAML complexity limit exceeded")
	}
	locations[pointer] = n
	if n.Anchor != "" || n.Kind == yaml.AliasNode {
		return nil, at(n, "anchors and aliases are unsupported")
	}
	switch n.Kind {
	case yaml.MappingNode:
		if n.Tag != "!!map" {
			return nil, at(n, "custom tags are unsupported")
		}
		result := map[string]any{}
		for i := 0; i < len(n.Content); i += 2 {
			key := n.Content[i]
			if key.Tag != "!!str" || key.Kind != yaml.ScalarNode || key.Value == "<<" {
				return nil, at(key, "mapping keys must be literal strings")
			}
			if _, ok := result[key.Value]; ok {
				return nil, at(key, "duplicate mapping key")
			}
			escaped := strings.ReplaceAll(strings.ReplaceAll(key.Value, "~", "~0"), "/", "~1")
			v, err := convert(n.Content[i+1], pointer+"/"+escaped, depth+1, budget, locations)
			if err != nil {
				return nil, err
			}
			result[key.Value] = v
		}
		return result, nil
	case yaml.SequenceNode:
		if n.Tag != "!!seq" {
			return nil, at(n, "custom tags are unsupported")
		}
		result := []any{}
		for i, item := range n.Content {
			v, err := convert(item, pointer+"/"+strconv.Itoa(i), depth+1, budget, locations)
			if err != nil {
				return nil, err
			}
			result = append(result, v)
		}
		return result, nil
	case yaml.ScalarNode:
		switch n.Tag {
		case "!!str":
			return n.Value, nil
		case "!!bool":
			if n.Value == "true" {
				return true, nil
			}
			if n.Value == "false" {
				return false, nil
			}
		case "!!int":
			v, err := strconv.ParseInt(n.Value, 10, 64)
			if err == nil {
				return float64(v), nil
			}
		}
	}
	return nil, at(n, "unsupported YAML value or tag")
}
