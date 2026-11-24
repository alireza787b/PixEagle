# Exact Ninja selection branch, PX4 155f415168cef08dca2f5d85d2bc258b44a589ec Makefile:85-108.
NINJA_BIN := ninja
ifndef NO_NINJA_BUILD
	NINJA_BUILD := $(shell $(NINJA_BIN) --version 2>/dev/null)

	ifndef NINJA_BUILD
		NINJA_BIN := ninja-build
		NINJA_BUILD := $(shell $(NINJA_BIN) --version 2>/dev/null)
	endif
endif

ifdef NINJA_BUILD
	PX4_CMAKE_GENERATOR := Ninja
	PX4_MAKE := $(NINJA_BIN)

	ifdef VERBOSE
		PX4_MAKE_ARGS := -v
	else
		PX4_MAKE_ARGS :=
	endif

	# Only override ninja default if -j is set.
	ifneq ($(j),)
		PX4_MAKE_ARGS := $(PX4_MAKE_ARGS) -j$(j)
	endif
endif

.PHONY: show
show:
	@printf '%s\n' '$(PX4_MAKE_ARGS)'
