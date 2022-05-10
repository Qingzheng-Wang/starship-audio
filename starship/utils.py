# Copyright (c) 2022 David Chan
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT


import os
import random
import string


def local_relpath(local_filepath: str, target_relative_filepath: str) -> str:
    """
    Generate an absolute path from a local **file** path, and a relative path from the file's containing directory.

    :param local_filepath: The local file to generate from
    :type local_filepath: str
    :param target_relative_filepath: The relative path
    :type target_relative_filepath: str
    :return: The absolute path.
    :rtype: str
    """
    return os.path.join(os.path.dirname(os.path.abspath(local_filepath)), target_relative_filepath)





def random_string(length: int, letters: str = string.ascii_lowercase) -> str:
    """
    Return a random string.

    :param length: The length of the string to return
    :type length: int
    :param letters: The letters to choose the string from, defaults to string.ascii_lowercase
    :type letters: Iterable[str], optional
    :return: The random string
    :rtype: str
    """
    return ''.join(random.choice(letters) for i in range(length))
