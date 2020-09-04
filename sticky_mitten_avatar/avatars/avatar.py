import matplotlib.pyplot
from typing import Dict, Union, List, Tuple, Optional
import numpy as np
from abc import ABC, abstractmethod
from ikpy.chain import Chain
from enum import Enum
from tdw.output_data import OutputData, AvatarStickyMittenSegmentationColors, AvatarStickyMitten, Bounds, Collision, \
    EnvironmentCollision
from tdw.tdw_utils import TDWUtils
from sticky_mitten_avatar.util import get_angle_between, rotate_point_around, FORWARD


class Arm(Enum):
    """
    The side that an arm is on.
    """

    left = 0,
    right = 1


class BodyPartStatic:
    """
    Static data for a body part in an avatar.
    """

    def __init__(self, o_id: int, color: Tuple[float, float, float], name: str):
        """
        :param o_id: The object ID of the part.
        :param color: The segmentation color of the part.
        :param name: The name of the body part.
        """

        self.o_id = o_id
        self.color = color
        self.name = name


class Joint:
    """
    A joint, a side, and an axis.
    """

    def __init__(self, part: str, arm: str, axis: str):
        """
        :param part: The name of the body part.
        :param axis: The axis of rotation.
        :param arm: The arm that the joint is attached to.
        """

        self.joint = f"{part}_{arm}"
        self.axis = axis
        self.arm = arm

    def __str__(self):
        return self.joint + " " + self.axis


class _IKGoal:
    """
    The goal of an IK action.
    """

    def __init__(self, target: Union[np.array, list, None], pick_up_id: int = None):
        """
        :param pick_up_id: If not None, the ID of the object to pick up.
        :param target: The target position of the mitten.
        """

        self.pick_up_id = pick_up_id
        if target is not None and isinstance(target, list):
            self.target = np.array(target)
        else:
            self.target = target


class Avatar(ABC):
    """
    High-level API for a sticky mitten avatar.
    Do not use this class directly; it is an abstract class. Use the `Baby` class instead (a subclass of `Avatar`).

    Fields:

    - `id` The ID of the avatar.
    - `body_parts_static` Static body parts data. Key = the name of the part. See `BodyPartsStatic`
    - `frame` Dynamic info for the avatar on this frame, such as its position. See `tdw.output_data.AvatarStickyMitten`
    """

    JOINTS: List[Joint] = [Joint(arm="left", axis="pitch", part="shoulder"),
                           Joint(arm="left", axis="yaw", part="shoulder"),
                           Joint(arm="left", axis="roll", part="shoulder"),
                           Joint(arm="left", axis="pitch", part="elbow"),
                           Joint(arm="left", axis="roll", part="wrist"),
                           Joint(arm="left", axis="pitch", part="wrist"),
                           Joint(arm="right", axis="pitch", part="shoulder"),
                           Joint(arm="right", axis="yaw", part="shoulder"),
                           Joint(arm="right", axis="roll", part="shoulder"),
                           Joint(arm="right", axis="pitch", part="elbow"),
                           Joint(arm="right", axis="roll", part="wrist"),
                           Joint(arm="right", axis="pitch", part="wrist")]
    # Additional force applied to bending joints.
    _BEND_FORCE = 80
    # Damper delta when bending joints.
    _BEND_DAMPER = -300

    def __init__(self, resp: List[bytes], avatar_id: str = "a", debug: bool = False):
        """
        :param resp: The response from the build after creating the avatar.
        :param avatar_id: The ID of the avatar.
        :param debug: If True, print debug statements.
        """

        self.id = avatar_id
        self._debug = debug
        # Set the arm chains.
        self._arms: Dict[Arm, Chain] = {Arm.left: self._get_left_arm(),
                                        Arm.right: self._get_right_arm()}
        # Any current IK goals.
        self._ik_goals: Dict[Arm, Optional[_IKGoal]] = {Arm.left: None,
                                                        Arm.right: None}
        smsc: Optional[AvatarStickyMittenSegmentationColors] = None
        for i in range(len(resp) - 1):
            r_id = OutputData.get_data_type_id(resp[i])
            if r_id == "smsc":
                q = AvatarStickyMittenSegmentationColors(resp[i])
                if q.get_id() == avatar_id:
                    smsc = q
                    break
        assert smsc is not None, f"No avatar segmentation colors found for {avatar_id}"
        # Cache static data of body parts.
        self.body_parts_static: Dict[int, BodyPartStatic] = dict()
        for i in range(smsc.get_num_body_parts()):
            body_part_id = smsc.get_body_part_id(i)
            bps = BodyPartStatic(o_id=body_part_id,
                                 color=smsc.get_body_part_segmentation_color(i),
                                 name=smsc.get_body_part_name(i))
            self.body_parts_static[body_part_id] = bps

        # Get data for the current frame.
        # Start dynamic data.
        self.frame = self._get_frame(resp)
        self.collisions: Dict[int, List[int]] = dict()
        self.env_collisions: List[int] = list()

    def can_bend_to(self, target: np.array, arm: Arm) -> bool:
        """
        :param target: The target position.
        :param arm: The arm that is bending to the target.

        :return: True if it is possible to move the mitten to the target.
        """

        pos = np.array([target[0], target[2]])
        d = np.linalg.norm(pos)
        if d < 0.25:
            if self._debug:
                print(f"Target {target} is too close to the avatar: {np.linalg.norm(d)}")
            return False
        if arm == Arm.left:
            d = np.linalg.norm(target - [-0.225, 0.565, 0.075])
        else:
            d = np.linalg.norm(target - [0.225, 0.565, 0.075])
        if d > 0.52:
            if self._debug:
                print(f"Target {target} is too far away from the {arm} shoulder: {d}")
            return False
        if target[2] < 0:
            if self._debug:
                print(f"Target {target} z < 0")
            return False
        return True

    def bend_arm(self, arm: Arm, target: np.array, target_orientation: np.array = None) -> List[dict]:
        """
        Get an IK solution to move a mitten to a target position.

        :param arm: The arm (left or right).
        :param target: The target position for the mitten.
        :param target_orientation: Target IK orientation. Usually you should leave this as None (the default).

        :return: A list of commands to begin bending the arm.
        """

        ik_target = np.array(target)

        angle = get_angle_between(v1=FORWARD, v2=self.frame.get_forward())
        target = rotate_point_around(point=ik_target, angle=angle) + self.frame.get_position()

        self._ik_goals[arm] = _IKGoal(target=target)

        # Get the IK solution.
        rotations = self._arms[arm].inverse_kinematics(target_position=ik_target, target_orientation=target_orientation)
        commands = []
        if self._debug:
            print([np.rad2deg(r) for r in rotations])
            self._plot_ik(target=ik_target, arm=arm)

            # Show the target.
            commands.extend([{"$type": "remove_position_markers"},
                             {"$type": "add_position_marker",
                              "position": TDWUtils.array_to_vector3(target)}])

        a = arm.name
        for c, r in zip(self._arms[arm].links[1:-1], rotations[1:-1]):
            j = c.name.split("_")
            joint = f"{j[0]}_{a}"
            axis = j[1]
            # Apply the motion. Strengthen the joint.
            commands.extend([{"$type": "bend_arm_joint_to",
                             "angle": np.rad2deg(r),
                              "joint": joint,
                              "axis": axis,
                              "avatar_id": self.id},
                             {"$type": "adjust_joint_force_by",
                              "delta": Avatar._BEND_FORCE,
                              "joint": joint,
                              "axis": axis,
                              "avatar_id": self.id},
                             {"$type": "adjust_joint_damper_by",
                              "delta": Avatar._BEND_DAMPER,
                              "joint": joint,
                              "axis": axis,
                              "avatar_id": self.id}])
        return commands

    def pick_up(self, object_id: int, bounds: Bounds) -> (List[dict], Arm):
        """
        Begin to try to pick up an object,
        Get an IK solution to a target position.

        :param object_id: The ID of the target object.
        :param bounds: Bounds output data.

        :return: A list of commands to begin bending the arm and the arm doing the pick-up action.
        """

        center: Optional[np.array] = None

        # Get the nearest point on the bounds.
        for i in range(bounds.get_num()):
            if bounds.get_id(i) == object_id:
                center = np.array(bounds.get_center(i))
                break
        assert center is not None, f"Couldn't find center of object {object_id}"

        # Get the nearest mitten.
        left_mitten_position = np.array(self.frame.get_mitten_center_left_position())
        right_mitten_position = np.array(self.frame.get_mitten_center_right_position())
        d_left = np.linalg.norm(left_mitten_position - center)
        d_right = np.linalg.norm(right_mitten_position - center)
        if d_left <= d_right:
            arm = Arm.left
            mitten = left_mitten_position
        else:
            arm = Arm.right
            mitten = right_mitten_position

        target_orientation = (mitten - center) / np.linalg.norm(mitten - center)
        angle = get_angle_between(v1=FORWARD, v2=self.frame.get_forward())

        target = rotate_point_around(point=center - self.frame.get_position(), angle=-angle)

        commands = self.bend_arm(arm=arm, target=target, target_orientation=target_orientation)
        self._ik_goals[arm].pick_up_id = object_id
        return commands, arm

    def on_frame(self, resp: List[bytes]) -> List[dict]:
        """
        Update the avatar based on its current arm-bending goals and its state.
        If the avatar has achieved a goal (for example, picking up an object), it will stop moving that arm.

        :param resp: The response from the build.

        :return: A list of commands to pick up, stop moving, etc.
        """

        # Update dynamic data.
        frame = self._get_frame(resp=resp)
        # Update dynamic collision data.
        self.collisions.clear()
        self.env_collisions.clear()
        # Get each collision.
        for i in range(len(resp) - 1):
            r_id = OutputData.get_data_type_id(resp[i])
            if r_id == "coll":
                coll = Collision(resp[i])
                collider_id = coll.get_collider_id()
                collidee_id = coll.get_collidee_id()
                # Check if the collision includes a body part.
                if collider_id in self.body_parts_static and collidee_id not in self.body_parts_static:
                    if collider_id not in self.collisions:
                        self.collisions[collider_id] = []
                    self.collisions[collider_id].append(collidee_id)
                elif collidee_id in self.body_parts_static and collider_id not in self.body_parts_static:
                    if collidee_id not in self.collisions:
                        self.collisions[collidee_id] = []
                    self.collisions[collidee_id].append(collider_id)
            elif r_id == "enco":
                coll = EnvironmentCollision(resp[i])
                collider_id = coll.get_object_id()
                if collider_id in self.body_parts_static:
                    self.env_collisions.append(collider_id)

        # Check if IK goals are done.
        temp_goals: Dict[Arm, Optional[_IKGoal]] = dict()
        # Get commands for the next frame.
        commands: List[dict] = []
        for arm in self._ik_goals:
            # No IK goal on this arm.
            if self._ik_goals[arm] is None:
                temp_goals[arm] = None
            # This is a dummy IK goal. Let it run.
            elif self._ik_goals[arm].target is None:
                temp_goals[arm] = self._ik_goals[arm]
            else:
                # Is the arm at the target?
                if arm == Arm.left:
                    mitten_position = np.array(frame.get_mitten_center_left_position())
                else:
                    mitten_position = np.array(frame.get_mitten_center_right_position())
                # If we're at the position, stop.
                d = np.linalg.norm(mitten_position - self._ik_goals[arm].target)
                if d < 0.1:
                    if self._debug:
                        print(f"{arm.name} mitten is at target position {self._ik_goals[arm].target}. Stopping.")
                    commands.extend(self._stop_arms(arm=arm))
                    temp_goals[arm] = None
                else:
                    # Are we trying to pick up an object?
                    if self._ik_goals[arm].pick_up_id is not None:
                        # Did we pick up the object in the previous frame?
                        if self._ik_goals[arm].pick_up_id in frame.get_held_left() or self._ik_goals[arm]. \
                                pick_up_id in frame.get_held_right():
                            if self._debug:
                                print(f"{arm.name} mitten picked up {self._ik_goals[arm].pick_up_id}. Stopping.")
                            commands.extend(self._stop_arms(arm=arm))
                            temp_goals[arm] = None
                        # Keep bending the arm and trying to pick up the object.
                        else:
                            commands.extend([{"$type": "pick_up_proximity",
                                              "distance": 0.15,
                                              "radius": 0.1,
                                              "grip": 1000,
                                              "is_left": arm == Arm.left,
                                              "avatar_id": self.id,
                                              "object_ids": [self._ik_goals[arm].pick_up_id]},
                                             {"$type": "pick_up",
                                              "grip": 1000,
                                              "is_left": arm == Arm.left,
                                              "object_ids": [self._ik_goals[arm].pick_up_id],
                                              "avatar_id": self.id}])
                            temp_goals[arm] = self._ik_goals[arm]
                    # Keep bending the arm.
                    else:
                        temp_goals[arm] = self._ik_goals[arm]
                        self._ik_goals[arm].previous_distance = d
        self._ik_goals = temp_goals

        # Check if the arms are still moving.
        temp_goals: Dict[Arm, Optional[_IKGoal]] = dict()
        for arm in self._ik_goals:
            # No IK goal on this arm.
            if self._ik_goals[arm] is None:
                temp_goals[arm] = None
            else:
                # Get the past and present angles.
                if arm == Arm.left:
                    angles_0 = self.frame.get_angles_left()
                    angles_1 = frame.get_angles_left()
                else:
                    angles_0 = self.frame.get_angles_right()
                    angles_1 = frame.get_angles_right()
                # Is any joint still moving?
                moving = False
                for a0, a1 in zip(angles_0, angles_1):
                    if np.abs(a0 - a1) > 0.03:
                        moving = True
                        break
                # Keep moving.
                if moving:
                    temp_goals[arm] = self._ik_goals[arm]
                else:
                    if self._debug:
                        print(f"{arm.name} is no longer bending. Cancelling.")
                    temp_goals[arm] = None
        self._ik_goals = temp_goals
        self.frame = frame

        return commands

    def is_ik_done(self) -> bool:
        """
        :return: True if the IK goals are complete, False if the arms are still moving/trying to pick up/etc.
        """

        return self._ik_goals[Arm.left] is None and self._ik_goals[Arm.right] is None

    def put_down(self, reset_arms: bool = True) -> List[dict]:
        """
        Put down the object.

        :param reset_arms: If True, reset arm positions to "neutral".

        :return: A list of commands to put down the object.
        """

        commands = [{"$type": "put_down",
                     "is_left": True,
                     "avatar_id": self.id},
                    {"$type": "put_down",
                     "is_left": False,
                     "avatar_id": self.id}]
        if reset_arms:
            commands.extend(self.reset_arms())
        return commands

    def reset_arms(self) -> List[dict]:
        """
        :return: A list of commands to drop arms to their starting positions.
        """

        commands = []
        for j in self.JOINTS:
            commands.append({"$type": "bend_arm_joint_to",
                             "joint": j.joint,
                             "axis": j.axis,
                             "angle": 0,
                             "avatar_id": self.id})
        # Add some dummy IK goals.
        self.set_dummy_ik_goals()
        return commands

    def set_dummy_ik_goals(self) -> None:
        """
        Set "dummy" IK goals.
        There's no target, so the avatar will just bend the arms until they stop moving.
        """

        for arm in self._ik_goals:
            self._ik_goals[arm] = _IKGoal(target=None)

    def is_holding(self, object_id: int) -> (bool, Arm):
        """
        :param object_id: The ID of the object.

        :return: True if the avatar is holding the object and, if so, the arm holding the object.
        """

        if object_id in self.frame.get_held_left():
            return True, Arm.left
        elif object_id in self.frame.get_held_right():
            return True, Arm.right
        return False, Arm.left

    def _stop_arms(self, arm: Arm) -> List[dict]:
        """
        :param arm: The arm to stop.

        :return: Commands to stop all arm movement.
        """

        if arm == Arm.left:
            joints = Avatar.JOINTS[:6]
            angles = self.frame.get_angles_left()
        else:
            joints = Avatar.JOINTS[6:]
            angles = self.frame.get_angles_right()

        commands = []
        # Get the current angle and bend the joint to that angle.
        for j, a in zip(joints, angles):
            theta = float(a)
            if theta > 90:
                theta = 180 - theta
            # Set the joint positions to where they are.
            # Reset force and damper.
            commands.extend([{"$type": "bend_arm_joint_to",
                              "angle": theta,
                              "joint": j.joint,
                              "axis": j.axis,
                              "avatar_id": self.id},
                             {"$type": "adjust_joint_force_by",
                              "delta": -Avatar._BEND_FORCE,
                              "joint": j.joint,
                              "axis": j.axis,
                              "avatar_id": self.id},
                             {"$type": "adjust_joint_damper_by",
                              "delta": -Avatar._BEND_DAMPER,
                              "joint": j.joint,
                              "axis": j.axis,
                              "avatar_id": self.id}])
        return commands

    @abstractmethod
    def _get_left_arm(self) -> Chain:
        """
        :return: The IK chain of the left arm.
        """

        raise Exception()

    def _get_right_arm(self) -> Chain:
        """
        :return: The IK chain of the right arm.
        """

        raise Exception()

    def _get_frame(self, resp: List[bytes]) -> AvatarStickyMitten:
        """
        :param resp: The response from the build.

        :return: AvatarStickyMitten output data for this avatar on this frame.
        """
        for i in range(len(resp) - 1):
            r_id = OutputData.get_data_type_id(resp[i])
            if r_id == "avsm":
                avsm = AvatarStickyMitten(resp[i])
                if avsm.get_avatar_id() == self.id:
                    return avsm
        raise Exception(f"No avatar data found for {self.id}")

    def _plot_ik(self, target: np.array, arm: Arm) -> None:
        """
        Debug an IK solution by creating a plot.

        :param target: The target position.
        :param arm: The arm.
        """

        chain = self._arms[arm]

        ax = matplotlib.pyplot.figure().add_subplot(111, projection='3d')

        chain.plot(chain.inverse_kinematics(target_position=target), ax, target=target)
        matplotlib.pyplot.show()
