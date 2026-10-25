"""Select an already installed compiler for native unit tests; installs nothing."""
import os
import shutil
import subprocess
from pathlib import Path

Import("env", "projenv")

requested = os.environ.get("BASU_HOST_CXX")
clang = shutil.which("clang++")
if os.name == "nt":
    # Prefer the compiler bundled with the installed MSVC standard library.
    finder = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    if finder.is_file():
        installation = subprocess.check_output([str(finder), "-latest", "-products", "*", "-property", "installationPath"], text=True).strip()
        candidate = Path(installation) / "VC/Tools/Llvm/x64/bin/clang++.exe"
        if candidate.is_file():
            clang = str(candidate)
    if not clang:
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "LLVM/bin/clang++.exe"
        if candidate.is_file():
            clang = str(candidate)
compiler = requested or (None if shutil.which("g++") else clang)
if compiler:
    parent = str(Path(compiler).parent)
    build_environments = [env, projenv] + [builder.env for builder in env.GetLibBuilders()]
    for node in env.Flatten(env.get("PIOBUILDFILES", [])):
        if node.has_builder():
            build_environments.append(node.get_executor().get_build_env())
    for build_env in build_environments:
        build_env.PrependENVPath("PATH", parent)
        build_env.Replace(CXX='"' + compiler + '"', CC='"' + str(Path(compiler).with_name("clang.exe")) + '"', LINK='"' + compiler + '"')
        archiver = Path(compiler).with_name("llvm-ar.exe" if os.name == "nt" else "llvm-ar")
        if archiver.is_file():
            build_env.Replace(AR='"' + str(archiver) + '"', ARFLAGS=["rcs"], RANLIBCOM="")
