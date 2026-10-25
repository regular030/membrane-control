"""Avoid the Windows child-process command limit with long local SDK paths."""
import os

Import("env", "projenv")

if os.name == "nt":
    project = env.subst("$PROJECT_DIR")
    toolchain = env.PioPlatform().get_package_dir("toolchain-xtensa-esp32")
    build_environments = [env, projenv] + [builder.env for builder in env.GetLibBuilders()]
    pending = list(env.Flatten(env.get("PIOBUILDFILES", []) + env.get("LIBS", [])))
    seen_nodes = set()
    while pending:
        node = pending.pop()
        if id(node) in seen_nodes or not hasattr(node, "has_builder"):
            continue
        seen_nodes.add(id(node))
        if node.has_builder():
            build_environments.append(node.get_executor().get_build_env())
            pending.extend(env.Flatten(node.sources))
    seen = set()
    for build_env in build_environments:
        if id(build_env) in seen:
            continue
        seen.add(id(build_env))
        # GCC uses argv[0] when finding cc1plus. An absolute executable path also
        # avoids ambiguity with other ESP toolchains already on the user's PATH.
        if toolchain:
            binaries = os.path.join(toolchain, "bin")
            build_env.Replace(
                CC=os.path.join(binaries, "xtensa-esp32-elf-gcc.exe"),
                CXX=os.path.join(binaries, "xtensa-esp32-elf-g++.exe"),
                LINK=os.path.join(binaries, "xtensa-esp32-elf-g++.exe"),
            )
        for key in ("CPPPATH",):
            compact = []
            for value in build_env.get(key, []):
                path = build_env.subst(str(value))
                try:
                    compact.append(os.path.relpath(path, project) if os.path.isabs(path) else path)
                except ValueError:  # A different drive cannot be expressed relatively.
                    compact.append(path)
            # Preserve CPPPATH for dependency scanning; only override its emitted
            # compiler flags. SCons otherwise re-anchors relative CPPPATH entries
            # to the platform-builder directory rather than the compiler's cwd.
            build_env.Replace(_CPPINCFLAGS=["-I" + path.replace("\\", "/") for path in compact])
