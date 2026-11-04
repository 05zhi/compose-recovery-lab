package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/05zhi/compose-recovery-lab/internal/notify"
	"github.com/05zhi/compose-recovery-lab/internal/safeio"
	"github.com/05zhi/compose-recovery-lab/internal/state"
	"os"
	"strings"
)

func notifyCommand(args []string) int {
	f := flag.NewFlagSet("notify", flag.ContinueOnError)
	id := f.String("run", "", "exact attempt ID")
	hook := f.String("webhook-file", "", "private file containing authorized destination URL; absent prints event only")
	if f.Parse(args) != nil || f.NArg() != 0 || *id == "" {
		return 2
	}
	db, e := state.OpenDefault()
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		return 1
	}
	defer db.Close()
	r, e := db.Get(*id, true)
	if e != nil {
		return 1
	}
	event, send, e := notify.Failure(r.Report)
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		return 1
	}
	if !send {
		return 0
	}
	if *hook != "" {
		info, e := os.Lstat(*hook)
		if e != nil || info.Mode().Perm()&0077 != 0 {
			fmt.Fprintln(os.Stderr, "webhook file must be private")
			return 1
		}
		data, e := safeio.Read(*hook, 4096)
		if e != nil {
			return 1
		}
		if e = notify.Send(context.Background(), strings.TrimSpace(string(data)), event); e != nil {
			fmt.Fprintln(os.Stderr, e)
			return 1
		}
	}
	if json.NewEncoder(os.Stdout).Encode(event) != nil {
		return 1
	}
	return 0
}
