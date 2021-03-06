# `sma_controller.py`

## `StickyMittenAvatarController(FloorplanController)`

`from tdw.sticky_mitten_avatar.sma_controller import StickyMittenAvatarController`

High-level API controller for sticky mitten avatars.

```python
from sticky_mitten_avatar import StickyMittenAvatarController, Arm

c = StickyMittenAvatarController()

# Load a simple scene and create the avatar.
c.init_scene()

# Bend an arm.
task_status = c.reach_for_target(target={"x": -0.2, "y": 0.21, "z": 0.385}, arm=Arm.left)
print(task_status) # TaskStatus.success

# Get the segmentation color pass for the avatar after bending the arm.
# See FrameData.save_images and FrameData.get_pil_images
segmentation_colors = c.frames[-1].id_pass

c.end()
```

All parameters of type `Dict[str, float]` are Vector3 dictionaries formatted like this:

```json
{"x": -0.2, "y": 0.21, "z": 0.385}
```

`y` is the up direction.

To convert from or to a numpy array:

```python
from tdw.tdw_utils import TDWUtils

target = {"x": 1, "y": 0, "z": 0}
target = TDWUtils.vector3_to_array(target)
print(target) # [1 0 0]
target = TDWUtils.array_to_vector3(target)
print(target) # {'x': 1.0, 'y': 0.0, 'z': 0.0}
```

A parameter of type `Union[Dict[str, float], int]]` can be either a Vector3 or an integer (an object ID).

***

## Fields

- `frames` Dynamic data for all of the frames from the previous avatar API call (e.g. `reach_for_target()`). [Read this](frame_data.md) for a full API.
  The next time an API call is made, this list is cleared and filled with new data.

```python
# Get the segmentation colors and depth map from the most recent frame.
id_pass = c.frames[-1].id_pass
depth_pass = c.frames[-1].depth_pass
# etc.
```

- `static_object_data`: Static info for all objects in the scene. [Read this](static_object_info.md) for a full API.

```python
# Get the segmentation color of an object.
segmentation_color = c.static_object_info[object_id].segmentation_color
```

- `static_avatar_data` Static info for the avatar's body parts. [Read this](body_part_static.md) for a full API. Key = body part ID.

```python
for body_part_id in c.static_avatar_data:
    body_part = c.static_avatar_data[body_part_id]
    print(body_part.object_id) # The object ID of the body part (matches body_part_id).
    print(body_part.color) # The segmentation color.
    print(body_part.name) # The name of the body part.
```

## Functions

***

#### \_\_init\_\_

**`def __init__(self, port: int = 1071, launch_build: bool = True, demo: bool = False)`**


| Parameter | Description |
| --- | --- |
| port | The port number. |
| launch_build | If True, automatically launch the build. |
| demo | If True, this is a demo controller. The build will play back audio and set a slower framerate and physics time step. |

***

#### init_scene

**`def init_scene(self, scene: str = None, layout: int = None) -> None`**

Initialize a scene, populate it with objects, add the avatar, and set rendering options.
The controller by default will load a simple empty room:
```python
from sticky_mitten_avatar import StickyMittenAvatarController
c = StickyMittenAvatarController()
c.init_scene()
```
Set the `scene` and `layout` parameters in `init_scene()` to load an interior scene with furniture and props:
```python
from sticky_mitten_avatar import StickyMittenAvatarController
c = StickyMittenAvatarController()
c.init_scene(scene="floorplan_2b", layout=0)
```
Valid scenes and layouts:
| `scene` | `layout` |
| --- | --- |
| `"2a"`, `"2b"`, or `"2b"` | 0 |

| Parameter | Description |
| --- | --- |
| scene | The name of an interior floorplan scene. If None, the controller will load a simple empty room. |
| layout | The furniture layout of the floorplan. If None, the controller will load a simple empty room. |

***

#### communicate

**`def communicate(self, commands: Union[dict, List[dict]]) -> List[bytes]`**

Overrides [`Controller.communicate()`](https://github.com/threedworld-mit/tdw/blob/master/Documentation/python/controller.md).
Before sending commands, append any automatically-added commands (such as arm-bending or arm-stopping).
If there is a third-person camera, append commands to look at a target (see `add_overhead_camera()`).
After receiving a response from the build, update the `frame` data.

| Parameter | Description |
| --- | --- |
| commands | Commands to send to the build. |

_Returns:_  The response from the build.

***

#### reach_for_target

**`def reach_for_target(self, arm: Arm, target: Dict[str, float], do_motion: bool = True, check_if_possible: bool = True) -> TaskStatus`**

Bend an arm joints of an avatar to reach for a target position.
Possible [return values](task_status.md):
- `success` (The avatar's arm's mitten reached the target position.)
- `too_close_to_reach`
- `too_far_to_reach`
- `behind_avatar`
- `no_longer_bending`

| Parameter | Description |
| --- | --- |
| arm | The arm (left or right). |
| target | The target position for the mitten relative to the avatar. |
| do_motion | If True, advance simulation frames until the pick-up motion is done. |
| check_if_possible | If True, before bending the arm, check if the mitten can reach the target assuming no obstructions; if not, don't try to bend the arm. |

_Returns:_  A `TaskStatus` indicating whether the avatar can reach the target and if not, why.

***

#### grasp_object

**`def grasp_object(self, object_id: int, arm: Arm, do_motion: bool = True, check_if_possible: bool = True) -> TaskStatus`**

The avatar's arm will reach for the object. Per frame, the arm's mitten will try to "grasp" the object.
A grasped object is attached to the avatar's mitten and its ID will be in [`FrameData.held_objects`](frame_data.md). There may be some empty space between a mitten and a grasped object.
This task ends when the avatar grasps the object (at which point it will stop bending its arm), or if it fails to grasp the object (see below).
Possible [return values](task_status.md):
- `success` (The avatar picked up the object.)
- `too_close_to_reach`
- `too_far_to_reach`
- `behind_avatar`
- `no_longer_bending`
- `failed_to_pick_up`
- `bad_raycast`

| Parameter | Description |
| --- | --- |
| object_id | The ID of the target object. |
| do_motion | If True, advance simulation frames until the pick-up motion is done. |
| arm | The arm of the mitten that will try to grasp the object. |
| check_if_possible | If True, before bending the arm, check if the mitten can reach the target assuming no obstructions; if not, don't try to bend the arm. |

_Returns:_  A `TaskStatus` indicating whether the avatar picked up the object and if not, why.

***

#### drop

**`def drop(self, reset_arms: bool = True, do_motion: bool = True) -> TaskStatus`**

Drop any held objects and reset the arms to their neutral positions.

| Parameter | Description |
| --- | --- |
| reset_arms | If True, reset arm positions to "neutral". |
| do_motion | If True, advance simulation frames until the pick-up motion is done. |

***

#### reset_arms

**`def reset_arms(self, do_motion: bool = True) -> TaskStatus`**

Reset the avatar's arms to their neutral positions.

| Parameter | Description |
| --- | --- |
| do_motion | If True, advance simulation frames until the pick-up motion is done. |

***

#### turn_to

**`def turn_to(self, target: Union[Dict[str, float], int], force: float = 1000, stopping_threshold: float = 0.15) -> TaskStatus`**

Turn the avatar to face a target position or object.
Possible [return values](task_status.md):
- `success` (The avatar turned to face the target.)
- `turned_360`
- `too_long`

| Parameter | Description |
| --- | --- |
| target | Either the target position or the ID of the target object. |
| force | The force at which the avatar will turn. More force = faster, but might overshoot the target. |
| stopping_threshold | Stop when the avatar is within this many degrees of the target. |

_Returns:_  A `TaskStatus` indicating whether the avatar turned successfully and if not, why.

***

#### turn_by

**`def turn_by(self, angle: float, force: float = 1000, stopping_threshold: float = 0.15) -> TaskStatus`**

Turn the avatar by an angle.
Possible [return values](task_status.md):
- `success` (The avatar turned by the angle.)
- `too_long`

| Parameter | Description |
| --- | --- |
| angle | The angle to turn to in degrees. If > 0, turn clockwise; if < 0, turn counterclockwise. |
| force | The force at which the avatar will turn. More force = faster, but might overshoot the target. |
| stopping_threshold | Stop when the avatar is within this many degrees of the target. |

_Returns:_  A `TaskStatus` indicating whether the avatar turned successfully and if not, why.

***

#### go_to

**`def go_to(self, target: Union[Dict[str, float], int], turn_force: float = 1000, move_force: float = 80, turn_stopping_threshold: float = 0.15, move_stopping_threshold: float = 0.35, stop_on_collision: bool = True) -> TaskStatus`**

Move the avatar to a target position or object.
Possible [return values](task_status.md):
- `success` (The avatar arrived at the target.)
- `too_long`
- `overshot`
- `collided_with_something_heavy` (if `stop_on_collision == True`)
- `collided_with_environment` (if `stop_on_collision == True`)

| Parameter | Description |
| --- | --- |
| target | Either the target position or the ID of the target object. |
| turn_force | The force at which the avatar will turn. More force = faster, but might overshoot the target. |
| turn_stopping_threshold | Stop when the avatar is within this many degrees of the target. |
| move_force | The force at which the avatar will move. More force = faster, but might overshoot the target. |
| move_stopping_threshold | Stop within this distance of the target. |
| stop_on_collision | If True, stop moving when the object collides with a large object (mass > 90) or the environment (e.g. a wall). |

_Returns:_   A `TaskStatus` indicating whether the avatar arrived at the target and if not, why.

***

#### move_forward_by

**`def move_forward_by(self, distance: float, move_force: float = 80, move_stopping_threshold: float = 0.35, stop_on_collision: bool = True) -> TaskStatus`**

Move the avatar forward by a distance along the avatar's current forward directional vector.
Possible [return values](task_status.md):
- `success` (The avatar moved forward by the distance.)
- `turned_360`
- `too_long`
- `overshot`
- `collided_with_something_heavy` (if `stop_on_collision == True`)
- `collided_with_environment` (if `stop_on_collision == True`)

| Parameter | Description |
| --- | --- |
| distance | The distance that the avatar will travel. If < 0, the avatar will move backwards. |
| move_force | The force at which the avatar will move. More force = faster, but might overshoot the target. |
| move_stopping_threshold | Stop within this distance of the target. |
| stop_on_collision | If True, stop moving when the object collides with a large object (mass > 90) or the environment (e.g. a wall). |

_Returns:_  A `TaskStatus` indicating whether the avatar moved forward by the distance and if not, why.

***

#### shake

**`def shake(self, joint_name: str = "elbow_left", axis: str = "pitch", angle: Tuple[float, float] = (20, 30), num_shakes: Tuple[int, int] = (3, 5), force: Tuple[float, float] = (900, 1000)) -> None`**

Shake an avatar's arm for multiple iterations.
Per iteration, the joint will bend forward by an angle and then bend back by an angle.
The motion ends when all of the avatar's joints have stopped moving.

| Parameter | Description |
| --- | --- |
| joint_name | The name of the joint. |
| axis | The axis of the joint's rotation. |
| angle | Each shake will bend the joint by a angle in degrees within this range. |
| num_shakes | The avatar will shake the joint a number of times within this range. |
| force | The avatar will add strength to the joint by a value within this range. |

***

#### rotate_camera_by

**`def rotate_camera_by(self, pitch: float = 0, yaw: float = 0) -> None`**

Rotate an avatar's camera around each axis.
The head of the avatar won't visually rotate, as this could put the avatar off-balance.
Advances the simulation by 1 frame.

| Parameter | Description |
| --- | --- |
| pitch | Pitch (nod your head "yes") the camera by this angle, in degrees. |
| yaw | Yaw (shake your head "no") the camera by this angle, in degrees. |

***

#### reset_camera_rotation

**`def reset_camera_rotation(self) -> None`**

Reset the rotation of the avatar's camera.
Advances the simulation by 1 frame.

***

#### add_overhead_camera

**`def add_overhead_camera(self, position: Dict[str, float], target_object: Union[str, int] = None, cam_id: str = "c", images: str = "all") -> None`**

Add an overhead third-person camera to the scene.
1. `"cam"` (only this camera captures images)
2. `"all"` (avatars currently in the scene and this camera capture images)
3. `"avatars"` (only the avatars currently in the scene capture images)

| Parameter | Description |
| --- | --- |
| cam_id | The ID of the camera. |
| target_object | Always point the camera at this object or avatar. |
| position | The position of the camera. |
| images | Image capture behavior. Choices: |

***

#### end

**`def end(self) -> None`**

End the simulation. Terminate the build process.

***

