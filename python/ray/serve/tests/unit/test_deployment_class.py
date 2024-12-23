import itertools
import random
import sys
from typing import Dict, List

import pytest

from ray import serve
from ray.serve._private.config import DeploymentConfig


def get_random_dict_combos(d: Dict, n: int) -> List[Dict]:
    """Gets n random combinations of dictionary d.

    Returns:
        List of dictionary combinations of lengths from 0 to len(d). List
        contains n random combinations of d's elements.
    """

    # Shuffle dictionary without modifying original dictionary
    d = dict(random.sample(list(d.items()), len(d)))

    combos = []

    # Sample random combos of random size
    subset_sizes = list(range(len(d) + 1))
    random.shuffle(subset_sizes)

    for subset_size in subset_sizes:
        subset_combo_iterator = map(
            dict, itertools.combinations(d.items(), subset_size)
        )
        if len(combos) < n:
            subset_combos = list(
                itertools.islice(subset_combo_iterator, n - len(combos))
            )
            combos.extend(subset_combos)
        else:
            break

    return combos


class TestGetDictCombos:
    def test_empty(self):
        assert get_random_dict_combos({}, 1) == [{}]

    def test_basic(self):
        d = {"a": 1, "b": 2, "c": 3}
        combos = get_random_dict_combos(d, 8)

        # Sort combos for comparison (sort by length, break ties by value sum)
        combos.sort(key=lambda d: len(d) * 100 + sum(d.values()))

        assert combos == [
            # Dictionaries of length 0
            {},
            # Dictionaries of length 1
            *({"a": 1}, {"b": 2}, {"c": 3}),
            # Dictionaries of length 2
            *({"a": 1, "b": 2}, {"a": 1, "c": 3}, {"b": 2, "c": 3}),
            # Dictionaries of length 3
            {"a": 1, "b": 2, "c": 3},
        ]

    def test_len(self):
        d = {i: i + 1 for i in range(50)}
        assert len(get_random_dict_combos(d, 1000)) == 1000

    def test_randomness(self):
        d = {i: i + 1 for i in range(1000)}
        combo1 = get_random_dict_combos(d, 1000)[0]
        combo2 = get_random_dict_combos(d, 1000)[0]
        assert combo1 != combo2


class TestDeploymentOptions:
    # Deployment options mapped to sample input
    deployment_options = {
        "name": "test",
        "version": "abcd",
        "num_replicas": 1,
        "ray_actor_options": {},
        "user_config": {},
        "max_ongoing_requests": 10,
        "autoscaling_config": None,
        "graceful_shutdown_wait_loop_s": 10,
        "graceful_shutdown_timeout_s": 10,
        "health_check_period_s": 10,
        "health_check_timeout_s": 10,
    }

    deployment_option_combos = get_random_dict_combos(deployment_options, 1000)

    @pytest.mark.parametrize("options", deployment_option_combos)
    def test_user_configured_option_names(self, options: Dict):
        """Check that user_configured_option_names tracks the correct options.

        Args:
            options: Maps deployment option strings (e.g. "name",
                "num_replicas", etc.) to sample inputs. Pairs come from
                TestDeploymentOptions.deployment_options.
        """

        @serve.deployment(**options)
        def f():
            pass

        assert f._deployment_config.user_configured_option_names == set(options.keys())

    @pytest.mark.parametrize("options", deployment_option_combos)
    def test_user_configured_option_names_serialized(self, options: Dict):
        """Check user_configured_option_names after serialization.

        Args:
            options: Maps deployment option strings (e.g. "name",
                "num_replicas", etc.) to sample inputs. Pairs come from
                TestDeploymentOptions.deployment_options.
        """

        # init_kwargs requires independent serialization, so we omit it.
        if "init_kwargs" in options:
            del options["init_kwargs"]

        @serve.deployment(**options)
        def f():
            pass

        serialized_config = f._deployment_config.to_proto_bytes()
        deserialized_config = DeploymentConfig.from_proto_bytes(serialized_config)

        assert deserialized_config.user_configured_option_names == set(options.keys())

    @pytest.mark.parametrize(
        "option",
        [
            "num_replicas",
            "autoscaling_config",
            "user_config",
        ],
    )
    def test_nullable_options(self, option: str):
        """Check that nullable options can be set to None."""

        deployment_options = {option: None}

        # One of "num_replicas" or "autoscaling_config" must be provided.
        if option == "num_replicas":
            deployment_options["autoscaling_config"] = {
                "min_replicas": 1,
                "max_replicas": 5,
                "target_ongoing_requests": 5,
            }
        elif option == "autoscaling_config":
            deployment_options["num_replicas"] = 5

        # Deployment should be created without error.
        @serve.deployment(**deployment_options)
        def f():
            pass

    @pytest.mark.parametrize("options", deployment_option_combos)
    def test_options(self, options):
        """Check that updating options also updates user_configured_options_names."""

        @serve.deployment
        def f():
            pass

        f = f.options(**options)
        assert f._deployment_config.user_configured_option_names == set(options.keys())

    def test_eager_placement_group_validation(self):
        """Check that placement groups are validated early.

        Placement group bundles should be validated when the deployment is
        defined, not when it's deployed.
        """

        with pytest.raises(ValueError):

            # PG bundle with empty resources is invalid.
            @serve.deployment(
                placement_group_bundles=[{"CPU": 0, "GPU": 0}],
                ray_actor_options={"num_cpus": 0, "num_gpus": 0},
            )
            def f():
                pass

    def test_placement_group_strategy_without_bundles(self):
        """Check that specifying strategy requires also specifying bundles."""

        with pytest.raises(ValueError):

            # PG strategy without bundles is invalid.
            @serve.deployment(placement_group_strategy="PACK")
            def f():
                pass

        # PG strategy with bundles is valid.
        @serve.deployment(
            placement_group_strategy="PACK",
            placement_group_bundles=[{"CPU": 10}],
        )
        def g():
            pass


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", "-s", __file__]))
