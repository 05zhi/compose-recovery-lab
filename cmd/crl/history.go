package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/05zhi/compose-recovery-lab/internal/config"
	"github.com/05zhi/compose-recovery-lab/internal/planner"
	"github.com/05zhi/compose-recovery-lab/internal/runner"
	"github.com/05zhi/compose-recovery-lab/internal/state"
	"os"
	"path/filepath"
	"time"
)

func historyCommand(command string, args []string) int {
	f := flag.NewFlagSet(command, flag.ContinueOnError)
	id := f.String("run", "", "run or attempt ID")
	exact := f.Bool("attempt", false, "select exact attempt")
	limit := f.Int("limit", 50, "maximum history entries")
	format := f.String("format", "json", "json or html")
	configPath := f.String("config", "", "retry with validated config")
	if f.Parse(args) != nil || f.NArg() != 0 {
		return 2
	}
	db, err := state.OpenDefault()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	defer db.Close()
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if command == "history" {
		items, e := db.List(*limit, false)
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 1
		}
		for i := range items {
			items[i].Report = nil
		}
		if enc.Encode(items) != nil {
			return 1
		}
		return 0
	}
	if command == "recover" {
		lock, e := runner.Lock()
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 1
		}
		defer lock.Close()
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		defer cancel()
		if e = runner.Reconcile(ctx); e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 1
		}
		fmt.Println("recovery cleanup complete")
		return 0
	}
	if *id == "" {
		fmt.Fprintln(os.Stderr, "--run required")
		return 2
	}
	record, err := db.Get(*id, *exact)
	if err != nil {
		fmt.Fprintln(os.Stderr, "run not found")
		return 1
	}
	switch command {
	case "status":
		if enc.Encode(record) != nil {
			return 1
		}
		return 0
	case "report":
		if *format == "json" {
			fmt.Println(string(record.Report))
			return 0
		}
		if *format != "html" {
			return 2
		}
		data, e := os.ReadFile(filepath.Join(record.Dir, "report.html"))
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 1
		}
		fmt.Print(string(data))
		return 0
	case "retry":
		c, e := config.Load(*configPath)
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 2
		}
		p, e := planner.Build(c)
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 1
		}
		if record.Operation != "run" || (record.ConfigHash != "" && record.ConfigHash != p.ConfigHash) {
			fmt.Fprintln(os.Stderr, "retry requires the same run configuration")
			return 1
		}
		lock, e := runner.Lock()
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 1
		}
		defer lock.Close()
		duration, _ := time.ParseDuration(c.Runtime.Timeout)
		ctx, cancel := context.WithTimeout(context.Background(), duration)
		defer cancel()
		if e = runner.Reconcile(ctx); e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 1
		}
		dir, e := runner.RunConfigured(runner.CheckContext(runner.RetryContext(ctx, record.ID), c.Checks), p.WorkDir, c.Backup.Path, p.Images, p.ConfigHash, p.ManifestHash)
		fmt.Println("report:", filepath.Join(dir, "report.json"))
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 1
		}
		return 0
	}
	return 2
}
