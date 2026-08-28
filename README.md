# RC N1 Bridge

RC N1 Bridge turns a DJI RC-N1 remote into a low-latency virtual Xbox 360
controller for Windows drone simulators and other games.

The application is a clean-room implementation built around the public facts of
DJI's USB serial protocol. It does not pretend to be a DJI FPV controller. It
creates a normal XInput device, which is the broadly compatible path for games
such as Liftoff, Uncrashed, DRL, DCL, Zephyr, and similar simulators.

## What is improved

- One poll is sent at a time; each validated reply is mapped immediately.
- No busy-spin output thread and no fixed 100 ms/10 Hz delay.
- Both DUML header CRC and full packet CRC are checked before controls are used.
- Serial reads time out, disconnects are neutralized, and the bridge reconnects.
- Port detection is layered rather than tied to one product ID or exact name.
  Known `For Protocol` interfaces rank first, DJI USB identity is only a hint,
  changed-name devices can be protocol-probed, and `For Debug` is excluded.
- Inputs are clamped and support calibration, asymmetric ranges, dead zones,
  expo, per-axis inversion, optional smoothing, and configurable button output.
- Fn, record, photo/shutter, return-to-home, the Cine/Normal/Sport switch, and
  both camera-wheel directions can each be mapped to an Xbox button or disabled.
- Dependencies are small and pinned. There is no telemetry, networking,
  persistence service, shell execution, or background updater.
- A diagnostics mode can validate the controller without creating a virtual pad.

## Requirements

- Windows 10 or 11, 64-bit
- Python 3.10 or newer
- DJI's USB VCOM driver, normally installed by **DJI Assistant 2 (Consumer
  Drones Series)**
- ViGEmBus for Xbox-controller emulation

ViGEmBus is retired upstream but remains the backend used by `vgamepad`. Installing
`vgamepad` launches its bundled ViGEmBus installer. Review the driver prompt and
accept it only if you are comfortable installing that kernel driver.

## Install

Open PowerShell in this folder:

```powershell
.\scripts\setup.ps1
```

Then connect the powered-on RC-N1 through the **bottom USB-C port** between the
stick storage slots. Close DJI Assistant completely because it can lock the COM
port.

Start the desktop app:

```powershell
.\scripts\run.ps1
```

After setup, you can also double-click `run.bat` in the project folder.

The first setup may display the ViGEmBus installer. Complete it before pressing
**Start bridge**.

## Command line

Use the command wrapper from the project folder:

```powershell
# See how serial ports are ranked. This does not transmit anything.
.\scripts\rcn1.ps1 scan

# Safely validate input for 10 seconds without creating an Xbox controller.
.\scripts\rcn1.ps1 diagnose --seconds 10

# Force a port when automatic detection cannot recognize a changed name.
.\scripts\rcn1.ps1 diagnose --port COM5 --seconds 10

# Run without the GUI.
.\scripts\rcn1.ps1 run

# Capture center and endpoint calibration.
.\scripts\rcn1.ps1 calibrate
```

Use `scan --probe` to send a short, CRC-validated read request to ranked
candidates. Unknown serial devices are never probed unless you explicitly add
`--include-unknown`; an explicit `--port` is the safer compatibility escape hatch.

## Game setup

1. Start RC N1 Bridge and wait for the green **Connected** status.
2. Open Windows' game-controller panel (`joy.cpl`) if you want to verify the
   virtual Xbox device first.
3. Open the simulator's controller settings.
4. Select the Xbox 360 controller and run the simulator's axis calibration.
5. Bind physical left horizontal/vertical and right horizontal/vertical as the
   simulator requests. If a direction is reversed, open **Control mappings** and
   toggle that axis's **Invert** option.

All axes now use their direct direction by default. Older version-1 settings are
migrated away from the original inverted vertical defaults. Axis inversion stays
individually configurable because simulators disagree about axis orientation.

Camera-wheel and physical-button outputs default to **Disabled**, preventing an
unwanted menu action before you intentionally bind them. Open **Control
mappings** to assign any input to A/B/X/Y, shoulder buttons, stick clicks,
Start/Back, or a D-pad direction. The same Xbox button may be assigned to more
than one RC input safely.

The RC-N1 throttle stick springs to center, unlike a typical FPV radio. Most
simulators can still calibrate it, but the feel will differ from a non-centering
FPV throttle gimbal.

## Configuration

The GUI writes `%APPDATA%\RCN1Bridge\config.json`. Generate defaults without
opening the GUI with:

```powershell
.\scripts\rcn1.ps1 init-config
```

Useful settings include:

- `port`: `null` for automatic detection or a value such as `"COM5"`
- `probe_unknown_ports`: permit protocol probing of unrecognized serial devices
- `smoothing`: `0.0` for minimum latency; modest values such as `0.1` reduce noise
- `suppress_duplicate_reports`: avoids redundant XInput reports while sticks are still
- `camera_button_threshold`: wheel travel required before its mapped button is pressed
- `button_poll_interval`: number of stick packets between extended-button reads
- `*_button` settings: Xbox binding name, or `"NONE"` to disable that input
- per-axis `minimum`, `center`, `maximum`, `invert`, `deadzone`, and `expo`

## Safety and privacy

RC N1 Bridge talks only to the selected local serial port and the local virtual
gamepad driver. It performs no network requests. On a timeout or disconnect it
immediately sends a neutral virtual-controller report, retries after a bounded
delay, and releases all mapped buttons during shutdown. Firmware that does not
answer the optional extended-button command automatically falls back to axes-only
operation for that connection.

The project is unofficial. Use it at your own risk, close it before running DJI
Assistant, and never use it as part of real-aircraft control.

## Development

The test suite uses generated DUML packets and a fake serial device, so it does
not require hardware or ViGEmBus:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

See [ATTRIBUTION.md](ATTRIBUTION.md) for the protocol-research references. The
new implementation is licensed under the [MIT License](LICENSE).
