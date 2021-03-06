import numpy as np


class Transform:
    """
    Transform data for an object, avatar, body part, etc.

    ```python
    from sticky_mitten_avatar import StickyMittenAvatarController, Arm

    c = StickyMittenAvatarController()
    c.init_scene()

    # Print the position of the avatar per frame.
    for frame in c.frames:
        print(c.frame.avatar_transform.position)
    c.end()
    ```

    ***

    ## Fields:

    - `position` The position of the object as a numpy array.
    - `rotation` The rotation (quaternion) of the object as a numpy array.
    - `forward` The forward directional vector of the object as a numpy array.
    """

    def __init__(self, position: np.array, rotation: np.array, forward: np.array):
        """
        :param position: The position of the object as a numpy array.
        :param rotation: The rotation (quaternion) of the object as a numpy array.
        :param forward: The forward directional vector of the object as a numpy array.
        """

        self.position = position
        self.rotation = rotation
        self.forward = forward
