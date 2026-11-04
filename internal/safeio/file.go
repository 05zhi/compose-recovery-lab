// Package safeio provides bounded, nonblocking reads of stable regular files on Linux.
package safeio

import (
	"errors"
	"io"
	"os"
	"syscall"
)

func Open(name string, max int64) (*os.File, os.FileInfo, error) {
	before, err := os.Lstat(name)
	if err != nil {
		return nil, nil, errors.New("required file unavailable")
	}
	if !before.Mode().IsRegular() || before.Size() > max {
		return nil, nil, errors.New("expected bounded regular file (links and special files rejected)")
	}
	fd, err := syscall.Open(name, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, nil, errors.New("cannot safely open file")
	}
	f := os.NewFile(uintptr(fd), name)
	opened, err := f.Stat()
	if err != nil || !os.SameFile(before, opened) || !opened.Mode().IsRegular() {
		f.Close()
		return nil, nil, errors.New("file changed before read")
	}
	return f, before, nil
}
func Verify(name string, before os.FileInfo) error {
	after, err := os.Lstat(name)
	if err != nil || !after.Mode().IsRegular() || !os.SameFile(before, after) || before.Size() != after.Size() || !before.ModTime().Equal(after.ModTime()) {
		return errors.New("file changed during validation")
	}
	return nil
}
func Read(name string, max int64) ([]byte, error) {
	f, before, err := Open(name, max)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, max+1))
	if err != nil || int64(len(data)) > max {
		return nil, errors.New("bounded file read failed")
	}
	if err = Verify(name, before); err != nil {
		return nil, err
	}
	return data, nil
}
