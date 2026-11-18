import re

import jude_kernel


def test_kernel_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", jude_kernel.KERNEL_VERSION)
