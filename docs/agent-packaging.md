# Packaging the Windows agent

How the Python agent becomes an installable, signed Windows application. The PyInstaller build in this
repository has been run and smoke-tested (headless sign-in and session, plus the tray UI from the frozen
executable). The installer and signing steps are scripted but need tooling and a certificate that the
build machine must provide.

## 1. Build pipeline

```
pytest ──► PyInstaller (one-folder) ──► Authenticode sign ──► Inno Setup installer ──► sign installer
```

```powershell
cd agent
./packaging/build.ps1                                     # tests + bundle + smoke test
./packaging/build.ps1 -Installer -CertThumbprint <sha1>   # + signed installer
```

| File | Purpose |
|------|---------|
| `packaging/workpulse-agent.spec` | PyInstaller spec: windowed (no console), no UPX, version resource, icon |
| `packaging/entry.py` | Frozen entry point |
| `packaging/version-info.txt` | File/product version shown in Explorer and in Defender reputation |
| `packaging/make_icon.py` | Renders `workpulse.ico` from the tray artwork |
| `packaging/installer.iss` | Inno Setup script (per-user, silent-install aware) |
| `packaging/build.ps1` | The pipeline above |

**Why one-folder, not one-file:** a one-file build unpacks to `%TEMP%` on every start. That is slower,
it is a common antivirus heuristic trigger, and it leaves nothing stable to sign. The one-folder build
(about 57 MB) starts instantly, and every DLL can be signed and checked.

**Why no UPX:** packed executables are frequently flagged by endpoint protection.

## 2. Code signing

Sign `WorkPulseAgent.exe` and the installer with an **EV or OV Authenticode certificate**, using SHA-256
and an RFC 3161 timestamp (`signtool /fd SHA256 /tr <tsa> /td SHA256`). The timestamp keeps signatures
valid after the certificate expires. An EV certificate gives immediate SmartScreen reputation; OV
reputation builds over downloads. In CI, keep the key in an HSM or a cloud key vault (Azure Key Vault +
`AzureSignTool`), never on disk.

## 3. Installer design

* **Per-user install, no admin rights:** `%LOCALAPPDATA%\Programs\WorkPulse`. The agent must run in the
  employee's interactive session anyway: idle detection (`GetLastInputInfo`) and the tray icon only work
  there, and a Windows *service* in session 0 can see neither.
* **Start with Windows:** an `HKCU\…\Run` entry (`WorkPulseAgent.exe --minimized`). Employees can toggle it
  from the tray menu.
* **Uninstall:** runs `--sign-out` (reports the session end and forgets the device secret), removes the Run
  entry, and deletes `%LOCALAPPDATA%\WorkPulse\Agent` (encrypted credentials, queue, logs).
* **Upgrades:** the stable `AppId` makes a newer installer upgrade in place. `CloseApplications=yes` stops
  the running agent; its encrypted queue and session checkpoint survive the upgrade.

### Managed / silent deployment (Intune, SCCM, GPO)

```
WorkPulseAgentSetup-0.1.0.exe /VERYSILENT /SUPPRESSMSGBOXES ^
    /API=https://workpulse.example.com/api /CODE=WP-XXXX-XXXX-XXXX
```

`/API` writes `agent.ini`. `/CODE` enrols the device silently with an **admin-issued enrolment code**,
created under People → employee → Devices → Register device. The code is single-use and expires after
72 hours, so no employee password is ever handled by deployment tooling. Because the install is per-user,
target it at the **user** context in Intune (or use a logon script).

For an MSIX or Microsoft Store channel later, the same PyInstaller output can be wrapped with the MSIX
Packaging Tool. Note that MSIX virtualises `HKCU\…\Run`, so a `windows.startupTask` extension replaces it.

## 4. Auto-update (planned)

1. `GET /api/agent/releases/latest` returns the version, a download URL, and a SHA-256 hash plus signature.
2. The agent downloads the signed installer in the background and verifies both the hash and the
   Authenticode signature (`WinVerifyTrust`, pinned publisher) before running it.
3. It runs the installer with `/VERYSILENT /CLOSEAPPLICATIONS` at a quiet moment (no session running).
   Staged rollout percentages are controlled server-side.

## 5. Release checklist

- [ ] `pytest` (unit + fake API) green; `tests/test_e2e.py` green against staging
- [ ] Version bumped in `app/__init__.py`, `version-info.txt`, `installer.iss`
- [ ] Bundle and installer signed; `signtool verify /pa /v` passes
- [ ] Fresh-VM test: install, sign in, start/stop session, go offline, reconnect, uninstall
- [ ] Silent install with `/CODE` on a managed test device
- [ ] Defender / SmartScreen check on a clean machine

## Live viewing dependencies (Phase 7)

Live viewing adds `aiortc`, `av` (FFmpeg/libvpx), `mss` and `websockets`. All ship Windows wheels. PyInstaller
collects them through `pyinstaller-hooks-contrib`, but `av` bundles FFmpeg DLLs (~60 MB), so the installer
grows accordingly. After building, smoke-test a live stream from the packaged executable: missing codec
DLLs only show up when the first frame is encoded.
