"""
Tests for DatetimeArray
"""
import numpy as np
import pytest

from pandas.core.dtypes.dtypes import DatetimeTZDtype

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import DatetimeArray


class TestNonNano:
    @pytest.fixture(params=["s", "ms", "us"])
    def unit(self, request):
        return request.param

    @pytest.fixture
    def reso(self, unit):
        # TODO: avoid hard-coding
        return {"s": 7, "ms": 8, "us": 9}[unit]

    @pytest.mark.xfail(reason="_box_func is not yet patched to get reso right")
    def test_non_nano(self, unit, reso):
        arr = np.arange(5, dtype=np.int64).view(f"M8[{unit}]")
        dta = DatetimeArray._simple_new(arr, dtype=arr.dtype)

        assert dta.dtype == arr.dtype
        assert dta[0]._reso == reso

    @pytest.mark.filterwarnings(
        "ignore:weekofyear and week have been deprecated:FutureWarning"
    )
    @pytest.mark.parametrize(
        "field", DatetimeArray._field_ops + DatetimeArray._bool_ops
    )
    def test_fields(self, unit, reso, field):
        dti = pd.date_range("2016-01-01", periods=55, freq="D")
        arr = np.asarray(dti).astype(f"M8[{unit}]")

        dta = DatetimeArray._simple_new(arr, dtype=arr.dtype)

        res = getattr(dta, field)
        expected = getattr(dti._data, field)
        tm.assert_numpy_array_equal(res, expected)


class TestDatetimeArrayComparisons:
    # TODO: merge this into tests/arithmetic/test_datetime64 once it is
    #  sufficiently robust

    def test_cmp_dt64_arraylike_tznaive(self, comparison_op):
        # arbitrary tz-naive DatetimeIndex
        op = comparison_op

        dti = pd.date_range("2016-01-1", freq="MS", periods=9, tz=None)
        arr = DatetimeArray(dti)
        assert arr.freq == dti.freq
        assert arr.tz == dti.tz

        right = dti

        expected = np.ones(len(arr), dtype=bool)
        if comparison_op.__name__ in ["ne", "gt", "lt"]:
            # for these the comparisons should be all-False
            expected = ~expected

        result = op(arr, arr)
        tm.assert_numpy_array_equal(result, expected)
        for other in [
            right,
            np.array(right),
            list(right),
            tuple(right),
            right.astype(object),
        ]:
            result = op(arr, other)
            tm.assert_numpy_array_equal(result, expected)

            result = op(other, arr)
            tm.assert_numpy_array_equal(result, expected)


class TestDatetimeArray:
    def test_astype_to_same(self):
        arr = DatetimeArray._from_sequence(
            ["2000"], dtype=DatetimeTZDtype(tz="US/Central")
        )
        result = arr.astype(DatetimeTZDtype(tz="US/Central"), copy=False)
        assert result is arr

    @pytest.mark.parametrize("dtype", ["datetime64[ns]", "datetime64[ns, UTC]"])
    @pytest.mark.parametrize(
        "other", ["datetime64[ns]", "datetime64[ns, UTC]", "datetime64[ns, CET]"]
    )
    def test_astype_copies(self, dtype, other):
        # https://github.com/pandas-dev/pandas/pull/32490
        ser = pd.Series([1, 2], dtype=dtype)
        orig = ser.copy()

        warn = None
        if (dtype == "datetime64[ns]") ^ (other == "datetime64[ns]"):
            # deprecated in favor of tz_localize
            warn = FutureWarning

        with tm.assert_produces_warning(warn):
            t = ser.astype(other)
        t[:] = pd.NaT
        tm.assert_series_equal(ser, orig)

    @pytest.mark.parametrize("dtype", [int, np.int32, np.int64, "uint32", "uint64"])
    def test_astype_int(self, dtype):
        arr = DatetimeArray._from_sequence([pd.Timestamp("2000"), pd.Timestamp("2001")])

        if np.dtype(dtype).kind == "u":
            expected_dtype = np.dtype("uint64")
        else:
            expected_dtype = np.dtype("int64")
        expected = arr.astype(expected_dtype)

        warn = None
        if dtype != expected_dtype:
            warn = FutureWarning
        msg = " will return exactly the specified dtype"
        with tm.assert_produces_warning(warn, match=msg):
            result = arr.astype(dtype)

        assert result.dtype == expected_dtype
        tm.assert_numpy_array_equal(result, expected)

    def test_tz_setter_raises(self):
        arr = DatetimeArray._from_sequence(
            ["2000"], dtype=DatetimeTZDtype(tz="US/Central")
        )
        with pytest.raises(AttributeError, match="tz_localize"):
            arr.tz = "UTC"

    def test_setitem_str_impute_tz(self, tz_naive_fixture):
        # Like for getitem, if we are passed a naive-like string, we impute
        #  our own timezone.
        tz = tz_naive_fixture

        data = np.array([1, 2, 3], dtype="M8[ns]")
        dtype = data.dtype if tz is None else DatetimeTZDtype(tz=tz)
        arr = DatetimeArray(data, dtype=dtype)
        expected = arr.copy()

        ts = pd.Timestamp("2020-09-08 16:50").tz_localize(tz)
        setter = str(ts.tz_localize(None))

        # Setting a scalar tznaive string
        expected[0] = ts
        arr[0] = setter
        tm.assert_equal(arr, expected)

        # Setting a listlike of tznaive strings
        expected[1] = ts
        arr[:2] = [setter, setter]
        tm.assert_equal(arr, expected)

    def test_setitem_different_tz_raises(self):
        data = np.array([1, 2, 3], dtype="M8[ns]")
        arr = DatetimeArray(data, copy=False, dtype=DatetimeTZDtype(tz="US/Central"))
        with pytest.raises(TypeError, match="Cannot compare tz-naive and tz-aware"):
            arr[0] = pd.Timestamp("2000")

        ts = pd.Timestamp("2000", tz="US/Eastern")
        with pytest.raises(ValueError, match="US/Central"):
            with tm.assert_produces_warning(
                FutureWarning, match="mismatched timezones"
            ):
                arr[0] = ts
        # once deprecation is enforced
        # assert arr[0] == ts.tz_convert("US/Central")

    def test_setitem_clears_freq(self):
        a = DatetimeArray(pd.date_range("2000", periods=2, freq="D", tz="US/Central"))
        a[0] = pd.Timestamp("2000", tz="US/Central")
        assert a.freq is None

    @pytest.mark.parametrize(
        "obj",
        [
            pd.Timestamp("2021-01-01"),
            pd.Timestamp("2021-01-01").to_datetime64(),
            pd.Timestamp("2021-01-01").to_pydatetime(),
        ],
    )
    def test_setitem_objects(self, obj):
        # make sure we accept datetime64 and datetime in addition to Timestamp
        dti = pd.date_range("2000", periods=2, freq="D")
        arr = dti._data

        arr[0] = obj
        assert arr[0] == obj

    def test_repeat_preserves_tz(self):
        dti = pd.date_range("2000", periods=2, freq="D", tz="US/Central")
        arr = DatetimeArray(dti)

        repeated = arr.repeat([1, 1])

        # preserves tz and values, but not freq
        expected = DatetimeArray(arr.asi8, freq=None, dtype=arr.dtype)
        tm.assert_equal(repeated, expected)

    def test_value_counts_preserves_tz(self):
        dti = pd.date_range("2000", periods=2, freq="D", tz="US/Central")
        arr = DatetimeArray(dti).repeat([4, 3])

        result = arr.value_counts()

        # Note: not tm.assert_index_equal, since `freq`s do not match
        assert result.index.equals(dti)

        arr[-2] = pd.NaT
        result = arr.value_counts(dropna=False)
        expected = pd.Series([4, 2, 1], index=[dti[0], dti[1], pd.NaT])
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("method", ["pad", "backfill"])
    def test_fillna_preserves_tz(self, method):
        dti = pd.date_range("2000-01-01", periods=5, freq="D", tz="US/Central")
        arr = DatetimeArray(dti, copy=True)
        arr[2] = pd.NaT

        fill_val = dti[1] if method == "pad" else dti[3]
        expected = DatetimeArray._from_sequence(
            [dti[0], dti[1], fill_val, dti[3], dti[4]],
            dtype=DatetimeTZDtype(tz="US/Central"),
        )

        result = arr.fillna(method=method)
        tm.assert_extension_array_equal(result, expected)

        # assert that arr and dti were not modified in-place
        assert arr[2] is pd.NaT
        assert dti[2] == pd.Timestamp("2000-01-03", tz="US/Central")

    def test_fillna_2d(self):
        dti = pd.date_range("2016-01-01", periods=6, tz="US/Pacific")
        dta = dti._data.reshape(3, 2).copy()
        dta[0, 1] = pd.NaT
        dta[1, 0] = pd.NaT

        res1 = dta.fillna(method="pad")
        expected1 = dta.copy()
        expected1[1, 0] = dta[0, 0]
        tm.assert_extension_array_equal(res1, expected1)

        res2 = dta.fillna(method="backfill")
        expected2 = dta.copy()
        expected2 = dta.copy()
        expected2[1, 0] = dta[2, 0]
        expected2[0, 1] = dta[1, 1]
        tm.assert_extension_array_equal(res2, expected2)

        # with different ordering for underlying ndarray; behavior should
        #  be unchanged
        dta2 = dta._from_backing_data(dta._ndarray.copy(order="F"))
        assert dta2._ndarray.flags["F_CONTIGUOUS"]
        assert not dta2._ndarray.flags["C_CONTIGUOUS"]
        tm.assert_extension_array_equal(dta, dta2)

        res3 = dta2.fillna(method="pad")
        tm.assert_extension_array_equal(res3, expected1)

        res4 = dta2.fillna(method="backfill")
        tm.assert_extension_array_equal(res4, expected2)

        # test the DataFrame method while we're here
        df = pd.DataFrame(dta)
        res = df.fillna(method="pad")
        expected = pd.DataFrame(expected1)
        tm.assert_frame_equal(res, expected)

        res = df.fillna(method="backfill")
        expected = pd.DataFrame(expected2)
        tm.assert_frame_equal(res, expected)

    def test_array_interface_tz(self):
        tz = "US/Central"
        data = DatetimeArray(pd.date_range("2017", periods=2, tz=tz))
        result = np.asarray(data)

        expected = np.array(
            [
                pd.Timestamp("2017-01-01T00:00:00", tz=tz),
                pd.Timestamp("2017-01-02T00:00:00", tz=tz),
            ],
            dtype=object,
        )
        tm.assert_numpy_array_equal(result, expected)

        result = np.asarray(data, dtype=object)
        tm.assert_numpy_array_equal(result, expected)

        result = np.asarray(data, dtype="M8[ns]")

        expected = np.array(
            ["2017-01-01T06:00:00", "2017-01-02T06:00:00"], dtype="M8[ns]"
        )
        tm.assert_numpy_array_equal(result, expected)

    def test_array_interface(self):
        data = DatetimeArray(pd.date_range("2017", periods=2))
        expected = np.array(
            ["2017-01-01T00:00:00", "2017-01-02T00:00:00"], dtype="datetime64[ns]"
        )

        result = np.asarray(data)
        tm.assert_numpy_array_equal(result, expected)

        result = np.asarray(data, dtype=object)
        expected = np.array(
            [pd.Timestamp("2017-01-01T00:00:00"), pd.Timestamp("2017-01-02T00:00:00")],
            dtype=object,
        )
        tm.assert_numpy_array_equal(result, expected)

    @pytest.mark.parametrize("index", [True, False])
    def test_searchsorted_different_tz(self, index):
        data = np.arange(10, dtype="i8") * 24 * 3600 * 10**9
        arr = DatetimeArray(data, freq="D").tz_localize("Asia/Tokyo")
        if index:
            arr = pd.Index(arr)

        expected = arr.searchsorted(arr[2])
        result = arr.searchsorted(arr[2].tz_convert("UTC"))
        assert result == expected

        expected = arr.searchsorted(arr[2:6])
        result = arr.searchsorted(arr[2:6].tz_convert("UTC"))
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize("index", [True, False])
    def test_searchsorted_tzawareness_compat(self, index):
        data = np.arange(10, dtype="i8") * 24 * 3600 * 10**9
        arr = DatetimeArray(data, freq="D")
        if index:
            arr = pd.Index(arr)

        mismatch = arr.tz_localize("Asia/Tokyo")

        msg = "Cannot compare tz-naive and tz-aware datetime-like objects"
        with pytest.raises(TypeError, match=msg):
            arr.searchsorted(mismatch[0])
        with pytest.raises(TypeError, match=msg):
            arr.searchsorted(mismatch)

        with pytest.raises(TypeError, match=msg):
            mismatch.searchsorted(arr[0])
        with pytest.raises(TypeError, match=msg):
            mismatch.searchsorted(arr)

    @pytest.mark.parametrize(
        "other",
        [
            1,
            np.int64(1),
            1.0,
            np.timedelta64("NaT"),
            pd.Timedelta(days=2),
            "invalid",
            np.arange(10, dtype="i8") * 24 * 3600 * 10**9,
            np.arange(10).view("timedelta64[ns]") * 24 * 3600 * 10**9,
            pd.Timestamp("2021-01-01").to_period("D"),
        ],
    )
    @pytest.mark.parametrize("index", [True, False])
    def test_searchsorted_invalid_types(self, other, index):
        data = np.arange(10, dtype="i8") * 24 * 3600 * 10**9
        arr = DatetimeArray(data, freq="D")
        if index:
            arr = pd.Index(arr)

        msg = "|".join(
            [
                "searchsorted requires compatible dtype or scalar",
                "value should be a 'Timestamp', 'NaT', or array of those. Got",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            arr.searchsorted(other)

    def test_shift_fill_value(self):
        dti = pd.date_range("2016-01-01", periods=3)

        dta = dti._data
        expected = DatetimeArray(np.roll(dta._data, 1))

        fv = dta[-1]
        for fill_value in [fv, fv.to_pydatetime(), fv.to_datetime64()]:
            result = dta.shift(1, fill_value=fill_value)
            tm.assert_datetime_array_equal(result, expected)

        dta = dta.tz_localize("UTC")
        expected = expected.tz_localize("UTC")
        fv = dta[-1]
        for fill_value in [fv, fv.to_pydatetime()]:
            result = dta.shift(1, fill_value=fill_value)
            tm.assert_datetime_array_equal(result, expected)

    def test_shift_value_tzawareness_mismatch(self):
        dti = pd.date_range("2016-01-01", periods=3)

        dta = dti._data

        fv = dta[-1].tz_localize("UTC")
        for invalid in [fv, fv.to_pydatetime()]:
            with pytest.raises(TypeError, match="Cannot compare"):
                dta.shift(1, fill_value=invalid)

        dta = dta.tz_localize("UTC")
        fv = dta[-1].tz_localize(None)
        for invalid in [fv, fv.to_pydatetime(), fv.to_datetime64()]:
            with pytest.raises(TypeError, match="Cannot compare"):
                dta.shift(1, fill_value=invalid)

    def test_shift_requires_tzmatch(self):
        # since filling is setitem-like, we require a matching timezone,
        #  not just matching tzawawreness
        dti = pd.date_range("2016-01-01", periods=3, tz="UTC")
        dta = dti._data

        fill_value = pd.Timestamp("2020-10-18 18:44", tz="US/Pacific")

        msg = "Timezones don't match. 'UTC' != 'US/Pacific'"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(
                FutureWarning, match="mismatched timezones"
            ):
                dta.shift(1, fill_value=fill_value)

        # once deprecation is enforced
        # expected = dta.shift(1, fill_value=fill_value.tz_convert("UTC"))
        # tm.assert_equal(result, expected)

    def test_tz_localize_t2d(self):
        dti = pd.date_range("1994-05-12", periods=12, tz="US/Pacific")
        dta = dti._data.reshape(3, 4)
        result = dta.tz_localize(None)

        expected = dta.ravel().tz_localize(None).reshape(dta.shape)
        tm.assert_datetime_array_equal(result, expected)

        roundtrip = expected.tz_localize("US/Pacific")
        tm.assert_datetime_array_equal(roundtrip, dta)
