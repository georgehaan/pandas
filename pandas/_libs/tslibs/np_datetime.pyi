import numpy as np

class OutOfBoundsDatetime(ValueError): ...
class OutOfBoundsTimedelta(ValueError): ...

# only exposed for testing
def py_get_unit_from_dtype(dtype: np.dtype): ...
def py_td64_to_tdstruct(td64: int, unit: int) -> dict: ...
def astype_overflowsafe(
    arr: np.ndarray, dtype: np.dtype, copy: bool = ...
) -> np.ndarray: ...
def is_unitless(dtype: np.dtype) -> bool: ...
