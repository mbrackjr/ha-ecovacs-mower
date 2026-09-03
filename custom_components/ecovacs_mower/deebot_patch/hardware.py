#            applies unchanged.
#   xmp9ds — GOAT A1600 RTK (reported in issue #43, firmware 1.17.9 — the
#            reporter has not confirmed the patch yet). A different machine
#            from e4gqia above, not a second class string for it: the RTK and
#            LiDAR Pro variants of the A1600 ship separately. Upstream's
#            xmp9ds.py is byte-identical to 9bts2s.py apart from the docstring,
#            which here names the model outright ("DEEBOT GOAT A1600 RTK
#            Capabilities"), so the O800 RTK's patch applies unchanged.
SUPPORTED_CLASSES = ("2i0fns", "9bts2s", "2px96q", "77atlz", "e4gqia", "xmp9ds")

# ``spotArea`` has only been verified on the A1600 LiDAR Pro. Keep it limited to
# that class until the payload shape has been verified on other firmware/classes.
ZONE_AREA_CLASSES = ("e4gqia",)


async def patch_device_info(class_: str) -> None:
    """Replace the cached device definition with one where the mow bugs are fixed.

    Six corrections:

    * ``clean.action.command``: ``CleanV2`` publishes on ``clean_V2``, which