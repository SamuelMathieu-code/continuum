from typing import Callable, List

import numpy as np
from torchvision import transforms

from continuum.datasets import _ContinuumDataset
from continuum.scenarios import InstanceIncremental
from continuum.task_set import TaskSet


class TransformationIncremental(InstanceIncremental):
    """Continual Loader, generating datasets for the consecutive tasks.

    Scenario: Every task contains the same data with different transformations.
    It is a cheap way to create instance incremental scenarios.
    Moreover, it is easier to analyse what algorithms forget or not.
    Classic transformation incremental scenarios are "permutations" and "rotations".

    :param cl_dataset: A continual dataset.
    :param nb_tasks: Number of tasks in the continuum.
    :param incremental_transformations: list of transformations to apply to specific tasks
    :param base_transformations: List of transformation to apply to all tasks.
    """

    def __init__(
        self,
        cl_dataset: _ContinuumDataset,
        nb_tasks: int,
        incremental_transformations: List[List[Callable]],
        base_transformations: List[Callable] = None
    ):
        super().__init__(
            cl_dataset=cl_dataset, nb_tasks=nb_tasks, base_transformations=base_transformations
        )
        if incremental_transformations is None:
            raise ValueError("For this scenario a list transformation should be set")

        if nb_tasks != len(incremental_transformations):
            raise ValueError("The number of tasks is not equal to the number of transformation")

        self.inc_trsf = incremental_transformations
        self._nb_tasks = self._setup(nb_tasks)

    def get_task_index(self, nb_tasks, y):
        # all tasks have all labels, only the transformation change
        return y

    def get_task_transformation(self, task_index):
        return transforms.Compose(self.inc_trsf[task_index] + self.trsf.transforms)

    def update_task_indexes(self, task_index):
        new_t = np.ones(len(self.dataset[1])) * task_index
        self.dataset = (self.dataset[0], self.dataset[1], new_t)

    def __getitem__(self, task_index):
        """Returns a task by its unique index.

        :param task_index: The unique index of a task, between 0 and len(loader) - 1.
        :return: A train PyTorch's Datasets.
        """
        if isinstance(task_index, slice):
            raise ValueError(
                "Incremental training based on transformations "
                "does not support slice, please provide only integer."
            )
        elif task_index < 0:  # Support for negative index, e.g. -1 == last
            while task_index < 0:
                task_index += len(self)

        self.update_task_indexes(task_index)
        train = self._select_data_by_task(task_index)
        trsf = self.get_task_transformation(task_index)

        return TaskSet(*train, trsf, data_type=self.cl_dataset.data_type)
