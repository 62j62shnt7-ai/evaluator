# Offline packaging feasibility spike

Status: **Windows first-run portable bootstrap implemented; Windows acceptance pending**. The `Run UT Review.bat` shortcut now downloads an embedded Python runtime and pinned workbook-reader wheels into the application folder on first launch, then reuses that runtime. This runner is macOS, not a clean disconnected Windows 11 x64 machine, so no Windows execution or offline acceptance claim is made.

Observed local baseline on 4 November 2026:

- OS: macOS (host-provided environment; exact build not captured)
- Python: 3.14.6; target plan baseline is Python 3.12, so compatibility remains unverified
- openpyxl: 3.1.5
- pytest: unavailable; current acceptance checks use `unittest`
- intake/hash and workbook inventory checks: prior local baseline 0.14 s for four tests (developer machine, not release benchmark)
- selected workbook adapter checks: 3.14 s for three tests after replacing repeated random access in read-only mode with normal read-only-by-application openpyxl loads; includes full workbook open cost
- Clean Windows launch, moving the folder to a disconnected/managed computer, and Windows timing: pending

The runtime uses portable Python/openpyxl code with no OS-specific UI dependency yet. Treat local timings as development observations, not Windows release benchmarks. Engineering calculation code remains disabled.
