# Protocol research attribution

RC N1 Bridge is a new implementation and is licensed under MIT. Its structure,
control flow, configuration, tests, user interface, and output handling were
written for this project.

The DJI DUML command identifiers and the RC-N1 channel byte offsets were
cross-checked against these community research projects:

- `pverhaert/DJI_RCN1_for_drone_simulators`, revision
  `53f45b60b7b315c659acc30de419489f3569a73b`
- `IvanYaky/DJI_RC-N1_SIMULATOR_FLY_DCL`, revision
  `1eb5faecab2b8cebbcd57d139919ff71483556d9`
- `PixDale/DJI_RC-N3_Xbox_Controller_Emulator`, consulted for the independently
  implemented `0x27` extended-status command and published button/mode masks

No source file from either project was copied. In particular, this project uses
generated CRC loops instead of copied lookup tables and implements independent
stream framing, validation, reconnection, mapping, and virtual-output layers.

DJI, RC-N1, Xbox, and Windows are trademarks of their respective owners. This
project is unofficial and is not affiliated with or endorsed by DJI.
