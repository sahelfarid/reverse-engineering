# Frida Module — Feature Backlog (Top 100)

> **Scope.** This tracks Frida capabilities for our module
> (`adb/frida_manager.py`, `routes/frida.py`, `static/js/frida.js`). Items still open are
> marked **⬜ Pending implementation**; completed backlog items are **✅ Implemented**.
> All items are for **authorized testing only** (your own devices/apps or targets you
> have written permission to test), consistent with the rest of the toolkit.

## Current baseline (already implemented — for reference, not in the 100)

Server download/xz-decompress/cache by ABI, push/start/stop `frida-server` (root),
running-PID detection, process listing (Frida API with ADB fallback), attach to
PID/name, spawn+attach+resume, per-session message queue, one-way SSE stream with
heartbeat, fixed-window drain, detach, script store CRUD with three read-only templates,
name/size validation, and audit logging.

Installed engine: **frida 17.15.3**. Backlog items wired up so far: **#13** version-match
guard, **#25/#27** installed-app enumeration + frontmost shortcut, **#31/#32/#37** spawn
gating + pending-spawn queue + kill, **#39** detach-reason reporting, **#47/#48** RPC
exports + two-way `script.post`, **#49–#51** structured logs + QJS/V8 runtime +
eternalize, **#83/#84** full SSL-pinning and root-detection agents.
Still not wired: remote devices, child gating, `Compiler`, `PackageManager`,
`PortalService`, `FileMonitor`, snapshots, etc.

**Legend:** ⬜ Pending implementation · ✅ Implemented

---

## A. Device & Connection Management

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 1 | Remote device connect | Attach to a `frida-server` reachable over TCP (`host:port`), not just USB. | `DeviceManager.add_remote_device(addr)` / `frida.get_remote_device()` | ⬜ Pending implementation |
| 2 | Remote device auth token | Support `frida-server --token`-protected endpoints for remote connect. | `add_remote_device(addr, token=...)` | ⬜ Pending implementation |
| 3 | Remote device TLS | Connect to a TLS-enabled server with certificate pinning/verification options. | `add_remote_device(..., certificate=..., origin=...)` | ⬜ Pending implementation |
| 4 | Multi-device registry | Track and switch between several connected devices (USB + remote) in one UI. | `DeviceManager.enumerate_devices()` | ⬜ Pending implementation |
| 5 | Device add/remove events | Live-update device list on plug/unplug instead of manual refresh. | `device_manager.on('added'/'removed'/'changed')` | ⬜ Pending implementation |
| 6 | Device-lost handling | Detect `device.is_lost()` / `'lost'` and tear down its sessions cleanly. | `device.on('lost')`, `device.is_lost()` | ⬜ Pending implementation |
| 7 | Local device (Gadget-in-emulator) | Support `get_local_device()` for host-side / emulator injection flows. | `frida.get_local_device()` | ⬜ Pending implementation |
| 8 | System parameters readout | Surface OS/arch/access details Frida reports per device. | `device.query_system_parameters()` | ⬜ Pending implementation |
| 9 | Message bus channel | Expose the device signalling bus for portal/agent messaging. | `device.get_bus()` | ⬜ Pending implementation |
| 10 | Open service / channel | Generic access to device services and raw channels (e.g. dbus, socket). | `device.open_service()`, `device.open_channel()` | ⬜ Pending implementation |
| 11 | Unpair device | Remove pairing state for iOS-style/paired transports. | `device.unpair()` | ⬜ Pending implementation |
| 12 | Cancellable operations | Make long connects/downloads cancellable from the UI. | `frida.Cancellable` | ⬜ Pending implementation |

## B. frida-server & Gadget Provisioning

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 13 | Version-match guard | Refuse attach when Python `frida` and on-device `frida-server` versions differ. | Compare `frida.__version__` vs server `--version` | ✅ Implemented |
| 14 | Server checksum verify | Verify SHA-256 of downloaded `frida-server` before pushing. | Hash release asset vs published checksum | ⬜ Pending implementation |
| 15 | Custom listen address/port | Start `frida-server -l 0.0.0.0:PORT` for remote/lab access. | Pass `-l` when launching server | ⬜ Pending implementation |
| 16 | Server auth token setup | Launch `frida-server` with `--token` and store it for remote connect. | `frida-server --token` | ⬜ Pending implementation |
| 17 | Multiple server instances | Run several servers on distinct ports/dirs on one device. | Distinct remote paths + PIDs | ⬜ Pending implementation |
| 18 | Persistent server (Magisk) | Install `frida-server` as a Magisk module / init service for boot persistence. | Magisk module scaffold + `su` | ⬜ Pending implementation |
| 19 | Auto server update | Detect newer release and re-download/replace cached server. | GitHub releases API + cache invalidation | ⬜ Pending implementation |
| 20 | Frida Gadget (non-root) | Provide the Gadget `.so` for non-rooted injection. | Bundle `frida-gadget-<ver>-android-<arch>.so` | ⬜ Pending implementation |
| 21 | APK repackage with Gadget | Patch a target APK to load Gadget (objection-style `patchapk`). | apktool decode → inject `libgadget.so` + smali → rebuild → sign | ⬜ Pending implementation |
| 22 | Gadget config modes | Support Gadget `listen` / `connect` / `script` interaction modes via config. | `libgadget.config.so` JSON | ⬜ Pending implementation |
| 23 | inject_library into PID | Inject a Gadget/agent blob into a running process directly. | `device.inject_library_file/blob()` | ⬜ Pending implementation |
| 24 | Server log tail | Stream `/data/local/tmp/frida-server.log` to the console for diagnostics. | `adb shell tail -f` bridge | ⬜ Pending implementation |

## C. Process, Application & Spawn Control

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 25 | Installed-app enumeration | List installed apps (not just running procs) with identifier + name. | `device.enumerate_applications()` | ✅ Implemented |
| 26 | App icons & metadata | Show app icons and running/backgrounded state in the picker. | `enumerate_applications(scope='full')` | ⬜ Pending implementation |
| 27 | Frontmost app shortcut | One-click attach to the currently foregrounded app. | `device.get_frontmost_application()` | ✅ Implemented |
| 28 | Rich process query | Fetch a single process with metadata (path, parameters). | `device.get_process(name, scope=...)` | ⬜ Pending implementation |
| 29 | Spawn with argv/env/cwd | Spawn with custom arguments, environment, and working directory. | `device.spawn(program, argv=, envp=, cwd=)` | ⬜ Pending implementation |
| 30 | Spawn stdio capture | Capture child stdout/stderr into the console. | `spawn(..., stdio='pipe')` + `device.on('output')` | ⬜ Pending implementation |
| 31 | Spawn gating | Auto-suspend **every** new process to hook it before it runs. | `device.enable_spawn_gating()` + `'spawn-added'` | ✅ Implemented |
| 32 | Pending-spawn queue UI | Show/resume/kill spawn-gated processes awaiting decision. | `device.enumerate_pending_spawn()` | ✅ Implemented |
| 33 | Child gating (follow forks) | Follow `fork()`/`exec()` children so subprocesses stay instrumented. | `session.enable_child_gating()` + `'child-added'` | ⬜ Pending implementation |
| 34 | Pending-children queue UI | Show/resume/kill child-gated processes. | `device.enumerate_pending_children()` | ⬜ Pending implementation |
| 35 | Child/spawn signal stream | Surface `child-added/removed`, `spawn-added/removed` events live. | `device.on(...)` signals | ⬜ Pending implementation |
| 36 | Process-crash reporting | Report crashes with signal + native report/backtrace. | `device.on('process-crashed')` | ⬜ Pending implementation |
| 37 | Kill by PID/name | Kill a target process from the process table. | `device.kill(pid)` | ✅ Implemented |
| 38 | Send input to stdin | Feed bytes to a spawned target's stdin. | `device.input(pid, data)` | ⬜ Pending implementation |

## D. Session Lifecycle

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 39 | Detach-reason reporting | Report **why** a session ended (app quit, killed, connection lost). | `session.on('detached', reason)` | ✅ Implemented |
| 40 | Persistent/reconnecting sessions | Survive brief disconnects and re-attach automatically. | `attach(..., persist_timeout=...)` + reconnect | ⬜ Pending implementation |
| 41 | Multiple scripts per session | Load several scripts into one session and manage them independently. | Multiple `session.create_script()` | ⬜ Pending implementation |
| 42 | Session state polling | Reflect `is_detached()` in the UI and disable stale controls. | `session.is_detached()` | ⬜ Pending implementation |
| 43 | Concurrent multi-session UI | Run and switch between several attached sessions with separate consoles. | Registry already keyed by id; needs UI tabs | ⬜ Pending implementation |
| 44 | Session idle timeout / GC | Auto-detach and clean up abandoned sessions to free device resources. | Background reaper over `_sessions` | ⬜ Pending implementation |
| 45 | Peer (P2P) connection | Set up a WebRTC peer connection for high-throughput data. | `session.setup_peer_connection()` | ⬜ Pending implementation |
| 46 | Portal join | Join a session to a Frida Portal for centralized fleet control. | `session.join_portal()` | ⬜ Pending implementation |

## E. Script Engine & RPC

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 47 | RPC exports invocation | Call `rpc.exports` functions from the UI with JSON args and see returns. | `script.exports.<fn>(...)`, `script.list_exports()` | ✅ Implemented |
| 48 | Two-way messaging (post/recv) | Send messages **into** a running script, not just receive. | `script.post(message, data=)` + agent `recv()` | ✅ Implemented |
| 49 | Structured log handler | Route `console.log/warn/error` with levels and clean formatting. | `script.set_log_handler()` | ✅ Implemented |
| 50 | Runtime selection (QJS/V8) | Choose the JS runtime per script for compatibility/perf. | `create_script(..., runtime='qjs'|'v8')` | ✅ Implemented |
| 51 | Script eternalize | Keep a script running after the client detaches (fire-and-forget). | `script.eternalize()` | ✅ Implemented |
| 52 | Hot reload on save | Reload the active script into the live session when the file changes. | `FileMonitor` + recreate script | ⬜ Pending implementation |
| 53 | TypeScript/module compile | Bundle multi-file / TS agents with `frida-compile` before load. | `frida.Compiler().build()` | ⬜ Pending implementation |
| 54 | Precompiled bytecode | Load agents from compiled bytes for speed/obfuscation. | `session.compile_script()` / `create_script_from_bytes()` | ⬜ Pending implementation |
| 55 | Snapshot warmup | Use a heap snapshot to cut agent startup latency. | `session.snapshot_script()`, `create_script(..., snapshot=)` | ⬜ Pending implementation |
| 56 | Script debugger (Inspector) | Attach Chrome DevTools / V8 Inspector to a script. | `script.enable_debugger(port)` | ⬜ Pending implementation |
| 57 | Script interrupt/terminate | Interrupt a busy script or force-terminate a runaway one. | `script.interrupt()`, `script.terminate()` | ⬜ Pending implementation |
| 58 | Parametrized scripts | Inject named parameters (class, method, address) into templates at load. | Prepend a `const PARAMS = {...}` prelude | ⬜ Pending implementation |

## F. Native Instrumentation Primitives (surfaced as UI/agent features)

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 59 | Interceptor hook builder | Point-and-click hook of a native export (onEnter/onLeave arg+ret capture). | `Interceptor.attach(addr, {...})` | ⬜ Pending implementation |
| 60 | Function replace | Replace a native function implementation with a stub/override. | `Interceptor.replace()` + `NativeCallback` | ⬜ Pending implementation |
| 61 | Module browser | List loaded modules with base/size/path per process. | `Process.enumerateModules()` | ⬜ Pending implementation |
| 62 | Export/import/symbol browser | Browse a module's exports, imports, and symbols; resolve addresses. | `Module.enumerateExports/Imports/Symbols()` | ⬜ Pending implementation |
| 63 | Symbol/API resolver search | Search functions across modules by glob/regex pattern. | `ApiResolver('module'|'objc')` | ⬜ Pending implementation |
| 64 | Memory hexdump viewer | Read and render memory regions as hexdump in the UI. | `Memory.readByteArray()` + `hexdump()` | ⬜ Pending implementation |
| 65 | Memory write/patch | Patch bytes at an address (with protection handling). | `Memory.writeByteArray()`, `Memory.protect()` | ⬜ Pending implementation |
| 66 | Memory pattern scan | Scan mapped memory for byte/AOB patterns. | `Memory.scan()` / `scanSync()` | ⬜ Pending implementation |
| 67 | Memory map viewer | List memory ranges with protections. | `Process.enumerateRanges()` | ⬜ Pending implementation |
| 68 | Memory access monitor | Watch address ranges for read/write access (watchpoints). | `MemoryAccessMonitor.enable()` | ⬜ Pending implementation |
| 69 | Stalker code tracing | Trace executed basic blocks/instructions on a thread. | `Stalker.follow(threadId, {...})` | ⬜ Pending implementation |
| 70 | Coverage export (drcov) | Export Stalker coverage as DRcov for Ghidra/IDA/Lighthouse. | Stalker events → DRcov blob | ⬜ Pending implementation |
| 71 | Backtrace capture | Capture native backtraces at a hook and symbolicate them. | `Thread.backtrace()` + `DebugSymbol.fromAddress()` | ⬜ Pending implementation |
| 72 | CModule / inline hooks | Run compiled C at hotspots for low-overhead tracing. | `CModule(source)` | ⬜ Pending implementation |

## G. Java / Android Runtime Instrumentation (surfaced as UI/agent features)

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 73 | Loaded-class enumeration | List all loaded Java classes with live filtering. | `Java.enumerateLoadedClasses()` | ⬜ Pending implementation |
| 74 | Class-loader enumeration | Enumerate class loaders (needed for multi-dex/plugin classes). | `Java.enumerateClassLoaders()` | ⬜ Pending implementation |
| 75 | Method browser | List a class's methods/fields/overloads to pick hook targets. | `Java.use(cls)` reflection | ⬜ Pending implementation |
| 76 | Live method hook builder | Hook a chosen Java method, log args/return, optionally override. | `Java.use().<m>.implementation = ...` | ⬜ Pending implementation |
| 77 | Overload-aware tracing | Hook all overloads of a method with correct signatures. | `.overloads.forEach(...)` | ⬜ Pending implementation |
| 78 | Heap instance search | Find live instances of a class and inspect/invoke them. | `Java.choose(cls, {...})` | ⬜ Pending implementation |
| 79 | Field dump / object stringify | Dump instance fields and stringify objects safely. | `Java.cast()` + reflection | ⬜ Pending implementation |
| 80 | Register/define class | Define a Java class at runtime (custom TrustManager, callbacks). | `Java.registerClass({...})` | ⬜ Pending implementation |
| 81 | Main-thread scheduling | Run instrumentation on the UI thread when required. | `Java.scheduleOnMainThread()` | ⬜ Pending implementation |
| 82 | Stack trace on Java hook | Capture Java call stacks at a hook for context. | `Java.use('java.lang.Exception')` trick | ⬜ Pending implementation |

## H. Ready-Made Bypass & Monitoring Modules (authorized testing)

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 83 | Full SSL-pinning bypass | Multi-framework unpinning (OkHttp, TrustManagerImpl, Conscrypt, WebView, Flutter, Cronet) — replace the current stub template. | Bundled maintained agent | ✅ Implemented (OkHttp/Conscrypt/TrustManager/WebView) |
| 84 | Full root-detection bypass | Broad root-check neutralizer (files, props, packages, `su`, SafetyNet/Play Integrity signals). | Bundled maintained agent | ✅ Implemented (files/exec/props/packages/RootBeer) |
| 85 | Anti-debug / anti-Frida bypass | Defeat common Frida/ptrace/port-scan/`/proc/maps` detections. | Hook detection routines | ⬜ Pending implementation |
| 86 | Crypto monitor | Log `Cipher`/`Mac`/`MessageDigest`/`KeyStore` inputs/outputs/keys. | Hook `javax.crypto.*` | ⬜ Pending implementation |
| 87 | Network/socket monitor | Trace socket connects, `OkHttp`/`HttpURLConnection` requests + bodies. | Hook net stack classes | ⬜ Pending implementation |
| 88 | File I/O monitor | Trace file opens/reads/writes and `SharedPreferences` access. | Hook `java.io.*` / prefs | ⬜ Pending implementation |
| 89 | SQLite query monitor | Log executed SQL and bound args. | Hook `SQLiteDatabase.*` | ⬜ Pending implementation |
| 90 | Intent / IPC monitor | Trace `startActivity`/`Intent` extras, broadcasts, deeplinks. | Hook `Intent`/`Context` | ⬜ Pending implementation |
| 91 | Clipboard monitor | Observe clipboard get/set operations. | Hook `ClipboardManager` | ⬜ Pending implementation |
| 92 | Biometric bypass | Force `BiometricPrompt`/`FingerprintManager` success paths in your own app. | Hook auth callbacks | ⬜ Pending implementation |

## I. Tooling / CLI Parity

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 93 | `frida-trace` builder | Include/exclude patterns auto-generate per-function handlers with live edit. | `ApiResolver` + generated stubs | ⬜ Pending implementation |
| 94 | REPL / interactive console | An interactive JS console bound to the live session (frida CLI parity). | `script.post` + `rpc.exports.eval` | ⬜ Pending implementation |
| 95 | `frida-discover` | Discover functions actually invoked during use (Stalker-based). | Stalker call events | ⬜ Pending implementation |
| 96 | File transfer via Frida | `frida-pull`/`frida-push` style transfer through the agent (no adb). | Agent `File` API + streaming | ⬜ Pending implementation |

## J. Console, Output & UX

| # | Feature | Details | Frida API / approach | Status |
|---|---------|---------|----------------------|--------|
| 97 | Persistent message log | Persist per-session messages to disk and reload on reconnect. | Append queue drains to a log file | ⬜ Pending implementation |
| 98 | Console export / download | Export session output as text/JSON; download binary `data` payloads. | Buffer + download endpoint | ⬜ Pending implementation |
| 99 | Console filter/search + pretty-print | Filter/search lines; pretty-render JSON payloads and `hexdump` blocks. | Frontend enhancement | ⬜ Pending implementation |
| 100 | Package manager integration | Install/query packages Frida-side for provisioning flows. | `frida.PackageManager` | ⬜ Pending implementation |

---

### Summary

| Category | Items | Done | Remaining | Status |
|---|---|---|---|---|
| A. Device & Connection Management | 1–12 | 0 | 12 | ⬜ Pending implementation |
| B. frida-server & Gadget Provisioning | 13–24 | 1 (#13) | 11 | ⬜ Partial |
| C. Process, Application & Spawn Control | 25–38 | 5 (#25, #27, #31, #32, #37) | 9 | ⬜ Partial |
| D. Session Lifecycle | 39–46 | 1 (#39) | 7 | ⬜ Partial |
| E. Script Engine & RPC | 47–58 | 5 (#47–#51) | 7 | ⬜ Partial |
| F. Native Instrumentation Primitives | 59–72 | 0 | 14 | ⬜ Pending implementation |
| G. Java / Android Runtime Instrumentation | 73–82 | 0 | 10 | ⬜ Pending implementation |
| H. Ready-Made Bypass & Monitoring Modules | 83–92 | 2 (#83, #84) | 8 | ⬜ Partial |
| I. Tooling / CLI Parity | 93–96 | 0 | 4 | ⬜ Pending implementation |
| J. Console, Output & UX | 97–100 | 0 | 4 | ⬜ Pending implementation |
| **Total** | **100** | **14** | **86** | **14 ✅ / 86 ⬜** |
