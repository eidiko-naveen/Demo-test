"""Kubernetes client configuration must honor the selected kubeconfig context."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from agent import tools


class KubeContextTests(TestCase):
    def test_external_config_uses_configured_context(self):
        settings = SimpleNamespace(
            kubeconfig_path="/tmp/example-kubeconfig",
            ocp_context="production-cluster",
        )

        with (
            patch("agent.tools.cfg", settings),
            patch("agent.tools.config.load_kube_config") as load_kube_config,
        ):
            tools._load_kube()

        load_kube_config.assert_called_once_with(
            config_file="/tmp/example-kubeconfig",
            context="production-cluster",
        )

    def test_in_cluster_config_does_not_use_kubeconfig(self):
        settings = SimpleNamespace(kubeconfig_path=None, ocp_context=None)

        with (
            patch("agent.tools.cfg", settings),
            patch("agent.tools.config.load_kube_config") as load_kube_config,
            patch("agent.tools.config.load_incluster_config") as load_incluster_config,
        ):
            tools._load_kube()

        load_incluster_config.assert_called_once_with()
        load_kube_config.assert_not_called()
