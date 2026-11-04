package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/05zhi/compose-recovery-lab/internal/runner"
)

func main() { os.Exit(run()) }
func run() int {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: crl backup|run|cleanup|doctor|plan [flags]")
		return 2
	}
	command := os.Args[1]
	if command == "notify" {
		return notifyCommand(os.Args[2:])
	}
	if command == "history" || command == "status" || command == "report" || command == "recover" || command == "retry" {
		return historyCommand(command, os.Args[2:])
	}
	if command != "backup" && command != "run" && command != "cleanup" && command != "doctor" && command != "plan" {
		fmt.Fprintln(os.Stderr, "unsupported command")
		return 2
	}
	flags := flag.NewFlagSet(command, flag.ContinueOnError)
	configFile := flags.String("config", "", "versioned drill YAML")
	offline := flags.Bool("offline", false, "doctor: validate bundle without querying Docker")
	home, _ := os.UserHomeDir()
	root := flags.String("work", filepath.Join(home, ".local", "state", "compose-recovery-lab", "runs"), "private Linux work directory")
	lockfile := flags.String("images", "examples/document-app/images.lock.json", "trusted local image lock")
	output := flags.String("out", "", "new backup bundle directory")
	bundle := flags.String("bundle", "", "completed local backup bundle")
	runDir := flags.String("run-dir", "", "run directory for cleanup")
	omit := flags.Bool("omit-attachment", false, "create a valid bundle missing one synthetic attachment")
	timeout := flags.Duration("timeout", 10*time.Minute, "total operation timeout; cleanup has independent 60s budget")
	if err := flags.Parse(os.Args[2:]); err != nil {
		return 2
	}
	if *configFile != "" || command == "doctor" || command == "plan" {
		invalid := *configFile == "" || flags.NArg() != 0 || (command != "doctor" && command != "plan" && command != "run")
		flags.Visit(func(f *flag.Flag) {
			if f.Name != "config" && !(command == "doctor" && f.Name == "offline") {
				invalid = true
			}
		})
		if invalid {
			fmt.Fprintln(os.Stderr, "--config cannot be mixed with legacy runtime overrides; --offline is doctor-only")
			return 2
		}
		return configured(command, *configFile, *offline)
	}
	if *offline {
		fmt.Fprintln(os.Stderr, "--offline requires doctor --config")
		return 2
	}
	if flags.NArg() != 0 || *timeout <= 0 || (command == "backup" && *output == "") || (command == "run" && *bundle == "") || (command == "cleanup" && *runDir == "") {
		fmt.Fprintln(os.Stderr, "missing or invalid flags")
		return 2
	}
	lock, err := runner.Lock()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	defer lock.Close()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	ctx, cancel := context.WithTimeout(ctx, *timeout)
	defer cancel()
	if command == "cleanup" {
		if err = runner.RecoverCleanup(ctx, *runDir); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		fmt.Println("cleanup complete")
		return 0
	}
	if err = runner.Reconcile(ctx); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	var images runner.Images
	data, err := os.ReadFile(*lockfile)
	if err == nil {
		err = json.Unmarshal(data, &images)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "cannot read trusted image lock:", err)
		return 1
	}
	var dir string
	if command == "backup" {
		dir, err = runner.Backup(ctx, *root, *output, images, *omit)
	} else {
		dir, err = runner.Run(ctx, *root, *bundle, images)
	}
	if dir != "" {
		fmt.Println("report:", filepath.Join(dir, "report.json"))
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}
