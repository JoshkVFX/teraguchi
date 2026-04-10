# Build the NvFBC capture helper used by screen_capture.py.
#
# The helper dlopens libnvidia-fbc.so.1 at runtime, so this only needs
# libc + libdl to link. The vendored NvFBC.h (MIT-licensed by NVIDIA,
# see the header comment) is the only dependency that isn't in the base
# toolchain.
#
# Targets:
#   make          — build ./nvfbc_capture
#   make clean    — remove the built binary
#
# Invoked by install-server.sh on NVIDIA hosts. Does nothing fancy on
# purpose; teragucci's Python code spawns this as a subprocess and
# reads raw frames from its stdout.

CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra -Wno-unused-parameter -std=c99
LDFLAGS ?=
LDLIBS  ?= -ldl

BIN     := nvfbc_capture
SRC     := nvfbc_capture.c

.PHONY: all clean
all: $(BIN)

$(BIN): $(SRC) NvFBC.h
	$(CC) $(CFLAGS) $(SRC) -o $(BIN) $(LDFLAGS) $(LDLIBS)

clean:
	rm -f $(BIN)
