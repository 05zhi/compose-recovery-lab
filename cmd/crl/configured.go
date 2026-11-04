package main

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/05zhi/compose-recovery-lab/internal/config"
	"github.com/05zhi/compose-recovery-lab/internal/doctor"
	"github.com/05zhi/compose-recovery-lab/internal/planner"
	"github.com/05zhi/compose-recovery-lab/internal/runner"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"
)

func configured(command, filename string, offline bool) int {
	c, err := config.Load(filename)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	p, err := planner.Build(c)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if command == "plan" {
		if err = encoder.Encode(p); err != nil {
			return 1
		}
		return 0
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	duration, _ := time.ParseDuration(c.Runtime.Timeout)
	ctx, cancel := context.WithTimeout(ctx, duration)
	defer cancel()
	readiness := doctor.CheckPlan(ctx, p, offline)
	if command == "doctor" {
		if err = encoder.Encode(readiness); err != nil {
			return 1
		}
		if readiness.Ready || offline {
			return 0
		}
		return 1
	}
	if !readiness.Ready {
		encoder.Encode(readiness)
		return 1
	}
	lock, err := runner.Lock()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	defer lock.Close()
	if err = runner.Reconcile(ctx); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	dir, err := runner.RunConfigured(runner.TemplateContext(runner.CheckContext(ctx, c.Checks), c.Template), p.WorkDir, c.Backup.Path, p.Images, p.ConfigHash, p.ManifestHash)
	if dir != "" {
		fmt.Println("report:", filepath.Join(dir, "report.json"))
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}
