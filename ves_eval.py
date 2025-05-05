import math
import sqlite3
import time

import numpy as np
from func_timeout import func_timeout, func_set_timeout, FunctionTimedOut


@func_set_timeout(timeout=10)
def execute_sql_returnTime(db_path, sql):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    start = time.time()
    cursor.execute(sql)
    end = time.time()
    conn.close()
    return end - start

@func_set_timeout(timeout=10)
def execute_sql_returnResultAndTime(db_path, sql):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    start = time.time()
    cursor.execute(sql)
    result = cursor.fetchall()
    end = time.time()
    conn.close()
    return result, end - start


def clean_abnormal(input):
    input = np.asarray(input)
    processed_list = []
    mean = np.mean(input, axis=0)
    std = np.std(input, axis=0)
    for x in input:
        if x < mean + 3 * std and x > mean - 3 * std:
            processed_list.append(x)
    return processed_list

def get_time_ratio(
    predicted_sql, ground_truth, db_path,exec_acc,iterate_num=10
):
    diff_list = []
    time_ratio = 0
    reward = 0
    if (exec_acc == 1):
        for _ in range(iterate_num):
            try:
                predicted_time = execute_sql_returnTime(db_path,predicted_sql)
            except Exception as e:
                return 0
            except FunctionTimedOut:
                return 0
            try:
                ground_truth_time = execute_sql_returnTime(db_path,ground_truth)
            except Exception as e:
                return 2
            except FunctionTimedOut:
                return 2
            diff_list.append(ground_truth_time / predicted_time)
        processed_diff_list = clean_abnormal(diff_list)
        time_ratio = sum(processed_diff_list) / len(processed_diff_list)
        if time_ratio == 0:
            reward = 0
        elif time_ratio >= 2:
            reward = 1.25
        elif time_ratio >= 1 and time_ratio < 2:
            reward = 1
        elif time_ratio >= 0.5 and time_ratio < 1:
            reward = 0.75
        elif time_ratio >= 0.25 and time_ratio < 0.5:
            reward = 0.5
        else:
            reward = 0.25
    return reward


def compute_ves(time_ratios):
    num_queries = len(time_ratios)
    total_ratio = 0
    count = 0

    for i, time_ratio in enumerate(time_ratios):
        if time_ratio != 0:
            count += 1
        total_ratio += math.sqrt(time_ratio) * 100
    ves = total_ratio / num_queries
    return ves

