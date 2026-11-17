import jude_kernel


def test_kernel_version_is_declared() -> None:
    assert jude_kernel.KERNEL_VERSION == "0.0.0"
