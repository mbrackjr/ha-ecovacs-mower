# Area-parameter capability design

This feature deliberately introduces a capability profile in
`deebot_patch/hardware.py` rather than another collection of model-specific
`*_CLASSES` tuples.

## Why `SUPPORTED_CLASSES` is changing

`SUPPORTED_CLASSES` used to answer one question: "which mower classes does the
patch layer know about?" That worked while every supported class received the
same patch. Area parameters introduce a second question: "which of those
classes has a particular capability whose wire values and semantics have been
independently validated?"

The profile mapping makes those two concepts explicit:

```python
SUPPORTED_CLASSES: dict[str, MowerProfile] = {
    "2i0fns": MowerProfile("2i0fns"),
    "9bts2s": MowerProfile("9bts2s"),
    "2px96q": MowerProfile("2px96q"),
    "77atlz": MowerProfile("77atlz"),
    "e4gqia": MowerProfile("e4gqia", area_parameters=True),
    "xmp9ds": MowerProfile("xmp9ds"),
}
```

The important part is not the dataclass itself; it is the direction of the
model. The device class remains the primary identity, while the profile says
which independently validated integration capabilities that identity gets.
This gives us one authoritative place to grow model capability information as
more features acquire hardware evidence.

For this PR there is exactly one new model-specific capability: `area_parameters`
on `e4gqia`. That is intentional. The area-parameter raw values and their
human-facing meanings have only been validated on the A1600 LiDAR Pro. A
matching field name in another mower's payload is not evidence that the same
numeric values mean the same thing.

## Why this is preferable to another `*_CLASSES` tuple

A tuple such as `AREA_PARAMETER_CLASSES = ("e4gqia",)` would encode the answer,
but it would scatter capability knowledge across increasingly many registries:
`SUPPORTED_CLASSES`, `ZONE_AREA_CLASSES`, `BORDER_CLASSES`, and eventually one
tuple for every new model-specific feature.

A profile scales in the other direction. The class remains the lookup key and
capabilities become properties of that class. Future additions can therefore
be expressed as another validated profile field without creating another
module-level registry and another membership check.

It also makes the distinction between support and validation visible in the
data structure. Being present in `SUPPORTED_CLASSES` means the integration can
patch the class. A capability flag means that the corresponding behavior has
additional evidence on that class. Those are deliberately different levels of
confidence.

The profile is not a second device-identity store. `deebot-client` remains the
source of the actual device identity. The profile is only integration metadata
keyed by that identity, and it contains no firmware conversion tables or
Home Assistant presentation details.

## Why the existing `ZONE_AREA_CLASSES` and `BORDER_CLASSES` remain for now

This PR intentionally does **not** convert the existing `ZONE_AREA_CLASSES`
or `BORDER_CLASSES` registries to profile fields.

Those registries already exist on `master`, have established behavior, and are
outside the area-parameter feature being reviewed here. Rewriting them at the
same time would mix an architectural refactor with a new protocol capability,
make the merge harder to review, and obscure whether the new area-parameter
behavior itself is correct.

They are therefore preserved exactly as the existing master functionality
requires. In particular, `e4gqia` continues to receive the validated `MowArea`
capability and `77atlz` continues to be the only class with the captured border
request shape.

The intent is not to defend two competing architectures forever. If the
maintainer agrees with the profile approach, those existing class-specific
registries can be migrated in a later, deliberately scoped change. That future
change can move their validated capability flags into `MowerProfile` and delete
the now-redundant tuples. Keeping that migration separate lets this PR establish
the pattern with one real use case instead of changing every existing feature
at once.

## Raw protocol values stay below HA

The profile only answers whether the capability exists. It does not contain
mowing-height conversions, speed conversions, obstacle-height conversions, or
angle mappings.

`deebot_patch` owns the Ecovacs wire representation and the authoritative raw
area snapshot. The HA layer owns the conversion between those raw values and
Home Assistant values. This is important because two mower classes can expose
fields with identical names while assigning different meanings or scales to
them.

The capability gate therefore happens before the HA entities are advertised,
while the representation mapping stays in `area_sensors.py`.

## Merge behavior with current master

The merge with `master` deliberately retains the existing zone-mowing and
border-mowing capability gates. The resulting A1600 profile therefore enables
both the already validated `MowArea` capability and the new area-parameter
refresh capability.

The patch also keeps `GetMapInfoV2` and the other newer refresh registrations
from `master`; resolving the conflict by taking the feature branch wholesale
would have silently removed those newer capabilities.

Finally, `patch_device_info()` does not return early merely because
`CleanMower` is already installed when the class is `e4gqia`. The area-parameter
feature is an additional event mapping, so the function must still be able to
install it when the common mower patch has already been applied. Other classes
retain the existing fast path.

## Scope boundary

This PR establishes the profile mechanism with the single capability required
by area-parameter support. It does not attempt to classify every model-specific
behavior already present in the repository. In particular, it does not widen
area parameters to another class, does not infer semantics from protocol field
names alone, and does not refactor the existing zone/border class registries.

That gives the maintainer a small, reviewable architectural decision now while
leaving the known follow-up cleanup explicit rather than hiding it inside this
feature PR.
