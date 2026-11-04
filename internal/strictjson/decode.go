// Package strictjson rejects duplicate keys, null, unknown and missing fields.
package strictjson

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"reflect"
	"strings"
)

func Decode(data []byte, out any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	budget := 10000
	value, err := value(decoder, 0, &budget)
	if err != nil {
		return err
	}
	if _, err = decoder.Token(); err != io.EOF {
		return errors.New("trailing JSON content")
	}
	if err = shape(value, reflect.TypeOf(out).Elem()); err != nil {
		return err
	}
	decoder = json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err = decoder.Decode(out); err != nil {
		return errors.New("invalid JSON field type or value")
	}
	return nil
}
func value(d *json.Decoder, depth int, budget *int) (any, error) {
	*budget--
	if depth > 24 || *budget < 0 {
		return nil, errors.New("JSON complexity limit exceeded")
	}
	token, err := d.Token()
	if err != nil {
		return nil, errors.New("invalid JSON syntax")
	}
	if token == nil {
		return nil, errors.New("null JSON fields are unsupported")
	}
	delim, ok := token.(json.Delim)
	if !ok {
		return token, nil
	}
	switch delim {
	case '{':
		m := map[string]any{}
		for d.More() {
			key, e := d.Token()
			if e != nil {
				return nil, errors.New("invalid object key")
			}
			s, ok := key.(string)
			if !ok {
				return nil, errors.New("object key must be string")
			}
			if _, ok = m[s]; ok {
				return nil, errors.New("duplicate JSON key")
			}
			v, e := value(d, depth+1, budget)
			if e != nil {
				return nil, e
			}
			m[s] = v
		}
		if _, err = d.Token(); err != nil {
			return nil, errors.New("invalid JSON object")
		}
		return m, nil
	case '[':
		a := []any{}
		for d.More() {
			v, e := value(d, depth+1, budget)
			if e != nil {
				return nil, e
			}
			a = append(a, v)
		}
		if _, err = d.Token(); err != nil {
			return nil, errors.New("invalid JSON array")
		}
		return a, nil
	}
	return nil, errors.New("unexpected JSON delimiter")
}
func shape(v any, t reflect.Type) error {
	// Types with custom JSON unmarshalling (e.g. time.Time) validate themselves later.
	if reflect.PointerTo(t).Implements(reflect.TypeOf((*json.Unmarshaler)(nil)).Elem()) {
		return nil
	}
	switch t.Kind() {
	case reflect.Struct:
		m, ok := v.(map[string]any)
		if !ok {
			return errors.New("expected JSON object")
		}
		fields := map[string]reflect.Type{}
		for i := 0; i < t.NumField(); i++ {
			field := t.Field(i)
			name := strings.Split(field.Tag.Get("json"), ",")[0]
			if name != "-" && name != "" {
				fields[name] = field.Type
			}
		}
		if len(m) != len(fields) {
			return errors.New("missing or unknown JSON field")
		}
		for name, kind := range fields {
			item, ok := m[name]
			if !ok {
				return errors.New("missing or unknown JSON field")
			}
			if err := shape(item, kind); err != nil {
				return err
			}
		}
	case reflect.Map:
		m, ok := v.(map[string]any)
		if !ok {
			return errors.New("expected JSON map")
		}
		for _, item := range m {
			if err := shape(item, t.Elem()); err != nil {
				return err
			}
		}
	case reflect.Slice:
		a, ok := v.([]any)
		if !ok {
			return errors.New("expected JSON array")
		}
		for _, item := range a {
			if err := shape(item, t.Elem()); err != nil {
				return err
			}
		}
	}
	return nil
}
