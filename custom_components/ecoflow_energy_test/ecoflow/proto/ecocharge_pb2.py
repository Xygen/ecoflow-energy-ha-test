"""Compatibility re-export for the integration-specific protobuf schema.

The implementation lives in ``ecoflow_energy_test_pb2`` so this custom
integration can run beside ``ecoflow_energy`` without registering the same
``ecocharge.proto`` file and ``ecoflow.*`` symbols in protobuf's global pool.
"""

from .ecoflow_energy_test_pb2 import *  # noqa: F403
from .ecoflow_energy_test_pb2 import DESCRIPTOR

