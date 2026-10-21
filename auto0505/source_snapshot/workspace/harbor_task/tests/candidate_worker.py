"""CPU-only interface and bounded stdlib module-origin policy.

Checks cover ordinary imports and supported file/dynamic loaders. This is not a
general-purpose secure Python interpreter or OS sandbox.
"""
import resource
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
import contextlib
import errno
import importlib.machinery
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import sysconfig


class ModuleOriginRejected(Exception):
    pass


def install_origin_policy(candidate):
    candidate = str(Path(candidate).resolve())
    candidate_cache = str(Path(importlib.util.cache_from_source(candidate)).resolve())
    roots = {str(Path(sysconfig.get_path(k)).resolve()) for k in ("stdlib", "platstdlib")}
    zip_roots = {str(Path(p).resolve()) for p in sys.path if p.endswith(".zip")}
    excluded_parts = {"site-packages", "dist-packages"}

    def allowed(origin):
        if isinstance(origin, (bytes, os.PathLike)):
            origin = os.fsdecode(origin)
        if origin in (None, "built-in", "frozen"):
            return True
        if not isinstance(origin, str):
            return False
        if origin.startswith("<frozen ") and origin.endswith(">"):
            return True
        if origin.startswith("<") and origin.endswith(">"):
            # In-memory computation is legal. This is not an authenticated
            # provenance proof for arbitrary user-created code objects.
            return origin in ("<string>", "<stdin>")
        value = str(Path(origin).resolve())
        if value == candidate:
            return True
        if excluded_parts.intersection(Path(value).parts):
            return False
        return any(value.startswith(root + os.sep) for root in roots | zip_roots)

    def require(origin):
        if not allowed(origin):
            raise ModuleOriginRejected("module_origin_outside_candidate_or_stdlib")

    def spec_check(spec):
        if spec is None:
            return
        require(spec.origin)
        if spec.submodule_search_locations is not None:
            for path in spec.submodule_search_locations:
                require(str(Path(path).resolve()) + os.sep)

    original_finders = tuple(sys.meta_path)

    class OriginFinder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.', 1)[0] not in sys.stdlib_module_names:
                raise ModuleOriginRejected("non_stdlib_import_requested")
            for finder in original_finders:
                method = getattr(finder, "find_spec", None)
                if method is None:
                    continue
                spec = method(fullname, path, target)
                if spec is not None:
                    spec_check(spec)
                    return spec
            return None

    sys.meta_path.insert(0, OriginFinder())
    # Direct spec_from_file_location(...).loader.exec_module(...) does not need
    # meta_path. Check actual loader filename before reading/executing code.
    for cls in (importlib.machinery.SourceFileLoader,
                importlib.machinery.SourcelessFileLoader,
                importlib.machinery.ExtensionFileLoader):
        for method_name in ("exec_module", "load_module", "get_code"):
            original = getattr(cls, method_name, None)
            if original is None:
                continue

            def checked(loader, *args, _original=original, **kwargs):
                require(getattr(loader, "path", None))
                return _original(loader, *args, **kwargs)

            setattr(cls, method_name, checked)

    def audit(event, args):
        if event == "import" and len(args) > 1 and args[1]:
            require(args[1])
        elif event == "open" and args and not isinstance(args[0], int):
            # CPython builtin open/io.open/os.open emit the same native audit
            # event, before opening the file. Readable external files would
            # let exec(open(helper).read()) hide its origin as <string>.
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            if (flags & os.O_ACCMODE) != os.O_WRONLY and not allowed(args[0]):
                # SourceFileLoader probes its fixed candidate bytecode cache
                # even with -B. Only an absent exact cache may be probed; no
                # cache bytes can be read, and the fresh scratch is root owned.
                origin = str(Path(os.fsdecode(args[0])).resolve())
                if origin != candidate_cache or Path(origin).exists():
                    raise ModuleOriginRejected("candidate_read_origin_outside_candidate_or_stdlib")
        elif event == "exec" and args:
            require(args[0].co_filename)
        elif event == "compile" and len(args) > 1:
            require(args[1])
        elif event == "ctypes.dlopen" and args and args[0] is not None:
            require(args[0])
        elif event in ("os.fork", "os.forkpty", "os.posix_spawn", "subprocess.Popen"):
            raise ModuleOriginRejected("candidate_subprocess_forbidden")

    sys.addaudithook(audit)
    initial_modules = set(sys.modules)

    def verify_loaded_origins():
        for name in set(sys.modules) - initial_modules:
            module = sys.modules.get(name)
            if module is not None:
                require(getattr(module, "__file__", None))
                spec_check(getattr(module, "__spec__", None))

    return verify_loaded_origins


def emit(value, code):
    sys.__stdout__.write(json.dumps(value, allow_nan=False) + "\n")
    sys.__stdout__.flush()
    return code


def main():
    emergency_reserve = bytearray(128 * 1024)
    try:
        check_origins = install_origin_policy(sys.argv[1])
        with contextlib.redirect_stdout(sys.stderr):
            spec = importlib.util.spec_from_file_location("candidate_method", sys.argv[1])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            fn = getattr(module, "get_timesteps", None)
            if not callable(fn):
                raise TypeError("missing_callable")
            result = [float(value) for value in fn(25, 1024)]
            check_origins()
        if not all(math.isfinite(value) for value in result):
            return emit({"schema_version": 1, "status": "HARD_GATE_INVALID", "reason_code": "schedule_nonfinite"}, 43)
        return emit({"schema_version": 1, "status": "NODES_READY", "timesteps": result}, 0)
    except ModuleOriginRejected as exc:
        return emit({"schema_version": 1, "status": "HARD_GATE_INVALID", "reason_code": str(exc)}, 43)
    except MemoryError:
        del emergency_reserve
        return emit({"schema_version": 1, "status": "RESOURCE_EXCEEDED", "reason_code": "candidate_address_space_exhausted"}, 44)
    except OSError as exc:
        if exc.errno in (errno.ENOMEM, errno.EAGAIN, errno.EFBIG):
            return emit({"schema_version": 1, "status": "RESOURCE_EXCEEDED", "reason_code": "candidate_resource_operation_denied"}, 44)
        return emit({"schema_version": 1, "status": "FORMAT_ERROR", "reason_code": "candidate_runtime_os_error"}, 42)
    except (SyntaxError, IndentationError, TypeError, ValueError, AttributeError, ImportError):
        return emit({"schema_version": 1, "status": "FORMAT_ERROR", "reason_code": "candidate_syntax_interface_or_value_format"}, 42)
    except Exception:
        return emit({"schema_version": 1, "status": "FORMAT_ERROR", "reason_code": "candidate_runtime_exception"}, 42)


if __name__ == "__main__":
    raise SystemExit(main())
