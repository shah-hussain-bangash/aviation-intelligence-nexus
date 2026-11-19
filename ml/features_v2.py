"""Stable import path for serialized schedule-feature transformations."""

import numpy as np


def time_features(frame):
    minutes = (frame["scheduled_departure_hour"].astype(float).to_numpy() * 60
               + frame["scheduled_departure_minute"].astype(float).to_numpy()) % 1440
    weekday = frame["day_of_week"].astype(float).to_numpy() - 1
    return np.column_stack([np.sin(2 * np.pi * minutes / 1440), np.cos(2 * np.pi * minutes / 1440),
                            np.sin(2 * np.pi * weekday / 7), np.cos(2 * np.pi * weekday / 7)])
