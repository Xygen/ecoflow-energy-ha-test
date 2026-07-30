"""Regression tests for coexistence with the regular EcoFlow integration."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from ecoflow_energy_test.ecoflow.proto import ecoflow_energy_test_pb2 as pb2


PB2_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "ecoflow_energy_test"
    / "ecoflow"
    / "proto"
    / "ecoflow_energy_test_pb2.py"
)


def test_descriptor_has_integration_specific_identity() -> None:
    assert pb2.DESCRIPTOR.name == "ecoflow_energy_test.proto"
    assert pb2.DESCRIPTOR.package == "ecoflow_energy_test"
    assert pb2.Header.DESCRIPTOR.full_name == "ecoflow_energy_test.Header"


@pytest.mark.parametrize("order", ["regular_first", "test_first"])
@pytest.mark.parametrize("divergent", [False, True])
def test_regular_and_test_schemas_can_share_a_process(order: str, divergent: bool) -> None:
    """Both import orders work even when the installed regular schema differs."""
    code = r'''
import importlib.util
import os

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

pool = descriptor_pool.Default()

def add_regular():
    file_proto = descriptor_pb2.FileDescriptorProto(
        name="ecocharge.proto", package="ecoflow", syntax="proto3"
    )
    header = file_proto.message_type.add(name="Header")
    field = header.field.add(
        name="pdata", number=1,
        label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
        type=descriptor_pb2.FieldDescriptorProto.TYPE_BYTES,
    )
    if os.environ["DIVERGENT"] == "1":
        header.field.add(
            name="newer_field", number=99,
            label=descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
            type=descriptor_pb2.FieldDescriptorProto.TYPE_UINT32,
        )
    pool.AddSerializedFile(file_proto.SerializeToString())

def load_test():
    spec = importlib.util.spec_from_file_location("isolated_test_pb2", os.environ["PB2_PATH"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

if os.environ["ORDER"] == "regular_first":
    add_regular()
    test_pb2 = load_test()
else:
    test_pb2 = load_test()
    add_regular()

regular_cls = message_factory.GetMessageClass(
    pool.FindMessageTypeByName("ecoflow.Header")
)
test_message = test_pb2.Header(pdata=b"powerglow")
regular_message = regular_cls()
regular_message.ParseFromString(test_message.SerializeToString())
assert regular_message.pdata == b"powerglow"

roundtrip = test_pb2.Header()
roundtrip.ParseFromString(regular_message.SerializeToString())
assert roundtrip.pdata == b"powerglow"
assert test_pb2.DESCRIPTOR.name == "ecoflow_energy_test.proto"
assert test_pb2.DESCRIPTOR.package == "ecoflow_energy_test"
'''
    env = os.environ.copy()
    env.update({
        "ORDER": order,
        "DIVERGENT": "1" if divergent else "0",
        "PB2_PATH": str(PB2_PATH),
    })
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

