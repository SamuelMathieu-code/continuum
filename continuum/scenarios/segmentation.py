import warnings
from copy import copy
from typing import Callable, List, Union, Optional

import numpy as np
from PIL import Image
import torchvision

from continuum.datasets import _ContinuumDataset
from continuum.scenarios import ClassIncremental
from continuum.tasks import TaskSet


class SegmentationClassIncremental(ClassIncremental):
    """Continual Loader, generating datasets for the consecutive tasks.

    Scenario: Each new tasks bring new classes only

    :param cl_dataset: A continual dataset.
    :param nb_tasks: The scenario number of tasks.
    :param increment: Either number of classes per task (e.g. increment=2),
                    or a list specifying for every task the amount of new classes
                     (e.g. increment=[5,1,1,1,1]).
    :param initial_increment: A different task size applied only for the first task.
                              Desactivated if `increment` is a list.
    :param transformations: A list of transformations applied to all tasks.
    :param class_order: An optional custom class order, used for NC.
                        e.g. [0,1,2,3,4,5,6,7,8,9] or [5,2,4,1,8,6,7,9,0,3]
    """

    def __init__(
        self,
        cl_dataset: _ContinuumDataset,
        nb_classes: int = 0,
        increment: Union[List[int], int] = 0,
        initial_increment: int = 0,
        transformations: List[Callable] = None,
        class_order: Optional[List[int]]=None,
        mode: str = "overlap",
        save_indexes: Optional[str] = None,
        test_background: bool = True
    ) -> None:
        self.mode = mode
        self.save_indexes = save_indexes
        self.test_background = test_background
        self._nb_classes = nb_classes

        super().__init__(
            cl_dataset=cl_dataset,
            increment=increment,
            initial_increment=initial_increment,
            class_order=class_order,
            transformations=transformations,
        )

    @property
    def nb_classes(self) -> int:
        """Total number of classes in the whole continual setting."""
        return len(np.unique(self.dataset[1]))  # type: ignore

    def __getitem__(self, task_index: Union[int, slice]):
        """Returns a task by its unique index.

        :param task_index: The unique index of a task. As for List, you can use
                           indexing between [0, len], negative indexing, or
                           even slices.
        :return: A train PyTorch's Datasets.
        """
        if isinstance(task_index, slice) and task_index.step is not None:
            raise ValueError("Step in slice for segmentation is not supported.")

        x, y, t, task_index = self._select_data_by_task(task_index)

        if self.mode in ("overlap", "disjoint"):
            labels = self._get_task_labels(task_index)

            inverted_order = {label: self.class_order.index(label) for label in labels}
            if not self.cl_dataset.train:
                inverted_order[0] = 0 if self.test_background else 255
                inverted_order[255] = 255

            label_trsf = torchvision.transforms.Lambda(
                lambda seg_map: seg_map.apply_(
                    lambda v: inverted_order.get(v, 0)
                )
            )

        return TaskSet(x, y, t, self.trsf, target_trsf=label_trsf, data_type=self.cl_dataset.data_type)

    def _get_task_labels(self, task_indexes: Union[int, List[int]]) -> List[int]:
        if isinstance(task_indexes, int):
            task_indexes = [task_indexes]

        labels = set()
        for t in task_indexes:
           previous_inc = sum(self._increments[:t])
           labels.update(
               self.class_order[previous_inc:previous_inc+self._increments[t]]
           )

        return list(labels)

    def _setup(self, nb_tasks: int) -> int:
        x, y, _ = self.cl_dataset.get_data()
        self.class_order = list(range(1, self._nb_classes + 1))

        self._increments = self._define_increments(
            self.increment, self.initial_increment, self.class_order
        )

        t = np.ones(len(x)) * -1
        accumulated_inc = 0
        t = _filter_images(
            y, self._increments, self.class_order, self.mode
        )
        self.dataset = (x, y, t)

        return len(self._increments)


def _filter_images(paths, increments, class_order, mode="overlap"):
    """Select images corresponding to the labels.

    Strongly inspired from Cermelli's code:
    https://github.com/fcdl94/MiB/blob/master/dataset/utils.py#L19
    """
    indexes_to_classes = []
    for path in paths:
        classes = np.unique(np.array(Image.open(path)).reshape(-1))
        indexes_to_classes.append(classes)

    t = np.zeros((len(paths), len(increments)))
    accumulated_inc = 0

    for task_id, inc in enumerate(increments):
        labels = class_order[accumulated_inc:accumulated_inc+inc]
        old_labels = class_order[:accumulated_inc]
        all_labels = labels + old_labels + [0, 255]

        for index, classes in enumerate(indexes_to_classes):
            if mode == "overlap":
                if any(c in labels for c in classes):
                    t[index, task_id] = 1
            elif mode == "disjoint":
                if any(c in labels for c in classes) and all(c in all_labels for c in classes):
                    t[index, task_id] = 1
            else:
                raise ValueError(f"Unknown mode={mode}.")

        accumulated_inc += inc

    return t
