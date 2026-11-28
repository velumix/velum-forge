"""Scene, collection, naming and metadata helpers shared by every Sun City asset.

Conventions (see tools/blender/README.md):
- Model in real-world meters. +Y = forward (bow / front), +X = right (starboard), +Z = up.
  The FBX export bakes `STUDS_PER_METER` into the vertices and the FBX axis conversion maps
  Blender +Y -> Roblox -Z, which is a Roblox part's LookVector.
- Every exported mesh carries `sc_part` (the MeshPart it is merged into).
- Empties named `SOCKET_<Name>` become Roblox Attachments; `SEAT_<Name>` become Seats.
"""

import math
import os

import bpy
from mathutils import Matrix, Vector

STUDS_PER_METER = 3.0  # 1.8 m human ~= 5.4 studs ~= R15 character height

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_BLENDER_DIR = os.path.dirname(LIB_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(TOOLS_BLENDER_DIR))
ASSET_ROOT = os.path.join(REPO_ROOT, "examples")


def _default_design_output_dir() -> str:
    env_dir = os.environ.get("VELUM_DESIGN_OUTPUT_DIR")
    if env_dir:
        return env_dir
    home = os.path.expanduser("~")
    onedrive_desk = os.path.join(home, "OneDrive", "Desktop", "Design Model Output")
    if os.path.isdir(os.path.join(home, "OneDrive", "Desktop")):
        return onedrive_desk
    return os.path.join(home, "Desktop", "Design Model Output")


DESIGN_OUTPUT_DIR = _default_design_output_dir()


def log(*args):
    print("[vflib]", *args)


def V(x=0.0, y=0.0, z=0.0):
    return Vector((x, y, z))


def ensure_object_mode():
    if bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------
_DATA_COLLECTIONS = ("meshes", "curves", "lights", "cameras")


def _free_data(data):
    if data is None or data.users:
        return
    for attr in _DATA_COLLECTIONS:
        coll = getattr(bpy.data, attr)
        try:
            if coll.get(data.name) == data:
                coll.remove(data)
                return
        except (TypeError, ReferenceError):
            continue


def clear_collection(col):
    """Delete every object (and child collection) inside `col`, freeing their data."""
    for child in list(col.children):
        clear_collection(child)
        bpy.data.collections.remove(child)
    for ob in list(col.objects):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        _free_data(data)


def fresh_collection(name, parent=None):
    """Return an empty collection called `name` linked under `parent` (scene root by default).

    Re-running a build script therefore only touches its own collection.
    """
    ensure_object_mode()
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    else:
        clear_collection(col)
    parent = parent or bpy.context.scene.collection
    if parent.children.get(col.name) is None:
        parent.children.link(col)
    return col


def set_collection_visible(col, visible=True):
    col.hide_viewport = not visible
    col.hide_render = not visible
    lc = _find_layer_collection(bpy.context.view_layer.layer_collection, col.name)
    if lc:
        lc.exclude = False
        lc.hide_viewport = not visible


def set_collection_tree_visible(col, visible=True):
    """Recursively show or hide `col` and all descendant child collections."""
    set_collection_visible(col, visible=visible)
    for child in col.children:
        set_collection_tree_visible(child, visible=visible)


def _find_layer_collection(lc, name):
    if lc.collection.name == name:
        return lc
    for child in lc.children:
        found = _find_layer_collection(child, name)
        if found:
            return found
    return None


def objects_in(col, types=("MESH",), recursive=True):
    obs = col.all_objects if recursive else col.objects
    return [o for o in obs if types is None or o.type in types]


# ---------------------------------------------------------------------------
# Objects & metadata
# ---------------------------------------------------------------------------
def link(ob, col, parent=None):
    col.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


def tag(ob, part=None, role=None, **props):
    """Attach Sun City export metadata to an object (stored as custom properties)."""
    if part is not None:
        ob["sc_part"] = part
    if role is not None:
        ob["sc_role"] = role
    for k, v in props.items():
        ob["sc_" + k] = v
    return ob


def empty(name, col, location=(0, 0, 0), rotation=(0, 0, 0), size=0.1, display="PLAIN_AXES", parent=None):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = display
    ob.empty_display_size = size
    ob.location = location
    ob.rotation_euler = rotation
    return link(ob, col, parent)


def socket(name, col, location, rotation=(0, 0, 0), parent_part=None, **props):
    """Create a `SOCKET_<name>` empty. Exported as a Roblox Attachment named `name`.

    Local axes: +Y = look (forward), +Z = up, and +Z is also the hinge axis when the socket
    drives a HingeConstraint. `parent_part` names the MeshPart that should own the attachment
    (defaults to the PrimaryPart).
    """
    ob = empty("SOCKET_" + name, col, location, rotation, size=0.12, display="ARROWS")
    ob["sc_socket"] = name
    if parent_part:
        ob["sc_parent_part"] = parent_part
    for k, v in props.items():
        ob["sc_" + k] = v
    return ob


def seat(name, col, location, yaw_deg=0.0, driver=False, size=(2.0, 1.0, 2.0)):
    """Create a `SEAT_<name>` empty. Exported as VehicleSeat (driver) or Seat. Faces local +Y."""
    ob = empty("SEAT_" + name, col, location, (0, 0, math.radians(yaw_deg)), size=0.25, display="CUBE")
    ob["sc_seat"] = name
    ob["sc_driver"] = bool(driver)
    ob["sc_size_studs"] = list(size)
    return ob


def world_bbox(objs):
    """Axis-aligned world bounding box (min, max) of evaluated mesh objects."""
    lo = Vector((1e18, 1e18, 1e18))
    hi = Vector((-1e18, -1e18, -1e18))
    any_pts = False
    for ob in objs:
        if ob.type != "MESH":
            continue
        for c in ob.bound_box:
            w = ob.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
            any_pts = True
    if not any_pts:
        return Vector(), Vector()
    return lo, hi


def axis_matrix(location, axis):
    """Matrix whose local +Z points along `axis`, translated to `location`."""
    axis = Vector(axis).normalized()
    rot = axis.to_track_quat("Z", "Y").to_matrix().to_4x4()
    return Matrix.Translation(Vector(location)) @ rot

