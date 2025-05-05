# 将字符串分割转换为数组,同时去除小数位置用于最后的判断
import ast
import contextlib
import io
import os
import re
import shutil
import sqlite3
import threading
from itertools import chain

import pandas as pd
from func_timeout import func_set_timeout


def flatten(lst):
    """将多维列表展平为一维列表"""
    return list(chain.from_iterable(flatten(i) if isinstance(i, list) else [i] for i in lst))


# 用于将打印的python数组转化为数组

def formatDataStr(data):
    # 使用,与空格与'与",\n分割数据
    data = re.split(r'[ ,\'\"\[\]\n\(\):{}]+', str(data).strip())
    data = [i.split('.')[0].lower() for i in data if i and i != 'None' and i != 'nan']
    data = [i for i in data if i != 'null'  and i != '0' and i != 'nan' and i != '(' and i != ')' and i != '']
    return data

def formatDataStr_set(data):
    return frozenset(formatDataStr(data))

def resultListEq(codeResult, sqlResult):
    # Define the string
    try:
        set1 = set(formatDataStr(str(codeResult)))
        set2 = set(formatDataStr([i for i in flatten(sqlResult) if i]))
        return set1 == set2
    except Exception as e:
        return False

def codeResultEq(codeResult1,codeResult2):
    try:
        set1 = set(formatDataStr(str(codeResult1)))
        set2 = set(formatDataStr(str(codeResult2)))
        return set1 == set2
    except Exception as e:
        return False


def resultListContain(List1, List2):
    """
    判断list1是否是list2的子集，又或者list2是list1的子集。当list1或list2为空时，返回False
    :param List1:
    :param List2:
    :return:
    """
    try:
        # Format and flatten the data for comparison
        set1 = set(formatDataStr(str(List1)))
        set2 = set(formatDataStr([i for i in flatten(List2) if i]))

        # Return False if either set is empty
        if not set1 or not set2:
            if not set1 and not set2:
                return True
            return False

        # Check for subset relationship
        return set1.issubset(set2) or set2.issubset(set1)
    except Exception as e:
        return False

def resultSqlListContainCode(code, sql):
    """
    判断list1是否是list2的子集，又或者list2是list1的子集。当list1或list2为空时，返回False
    :param List1:
    :param List2:
    :return:
    """
    try:
        # Format and flatten the data for comparison
        set1 = set(formatDataStr(str(sql)))
        set2 = set(formatDataStr([i for i in flatten([code]) if i]))
        # 如果sql为空，则返回False
        if not set1:
            return False

        # 如果code为空，返回False
        if not set2:
            return False

        # Check for subset relationship
        return set1.issubset(set2) or set2.issubset(set1)
    except Exception as e:
        return False
def resultSqlListEqCode(code,sql):
    try:
        set1 = set(formatDataStr(str(sql)))
        set2 = set(formatDataStr(str(code)))
        # 如果sql为空，则返回False
        if not set1:
            return False

        # 如果code为空，返回True
        if not set2:
            return True
        return set1 == set2
    except Exception as e:
        return False

def resultSqlListEqCode_codeNullFalse(code,sql):
    try:
        set1 = set(formatDataStr(str(sql)))
        set2 = set(formatDataStr(str(code)))
        # 如果sql为空，则返回True
        if not set1:
            return True

        # 如果code为空，返回False
        if not set2:
            return False
        return set1 == set2
    except Exception as e:
        return False


@func_set_timeout(3)
def execute_code_and_capture_print(code_string):
    # 创建一个 StringIO 对象来捕获输出
    code_output = io.StringIO()

    # 使用 contextlib.redirect_stdout 重定向标准输出到 StringIO 对象
    with contextlib.redirect_stdout(code_output):
        local_vars = {}
        # Execute the code string with local_vars as the local scope
        exec(code_string, {}, local_vars)
        # Extract the result from local_vars
        result = local_vars.get('result', None)
        # Check if result is a DataFrame
        if isinstance(result, pd.DataFrame):
            result = result.values.tolist()

        # Convert result to string
        # Check if result is None and handle accordingly
        if result is None:
            result_str = ""
        else:
            result_str = str(result).strip()

        # If result_str is not empty, return it
        if result_str:
            return result_str
    # 获取捕获的输出内容
    print_output = code_output.getvalue()

    return print_output

@func_set_timeout(3)
def run_code_get_array_result(code_string):
    # Create a StringIO object to capture the output
    code_output = io.StringIO()

    # Use contextlib.redirect_stdout to redirect standard output to the StringIO object
    with contextlib.redirect_stdout(code_output):
        local_vars = {}
        try:
            # Execute the code string with local_vars as the local scope
            exec(code_string, {}, local_vars)
        except Exception as e:
            return False, []
        # Extract the result from local_vars
        result = local_vars.get('result', None)
        # Check if result is a DataFrame
        if isinstance(result, pd.DataFrame):
            result = result.values.tolist()

        # If result is an array (list), return it
        if isinstance(result, list):
            return True, result

        # If result is not an array, try to convert print_output to an array
        print_output = code_output.getvalue()

        if print_output:
            try:
                # Attempt to safely evaluate the print output as a list using ast.literal_eval
                result_array = ast.literal_eval(print_output)
                if isinstance(result_array, list):
                    return True, result_array
                return True,[result_array]
            except (ValueError, SyntaxError):
                # If conversion fails, return False
                return False, []

    # If neither result nor print_output could be converted to a list, return False
    return False, []


def execute_sql(sqlite_path, sql_query):
    # 连接到 SQLite 数据库
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    try:
        # 执行 SQL 语句
        cursor.execute(sql_query)
        # 提交事务（如果是写操作）
        conn.commit()
        # 获取查询结果（如果是读操作）
        results = cursor.fetchall()
        return results
    finally:
        # 关闭数据库连接
        conn.close()

@func_set_timeout(3)
def execute_sql_with_timeout(sqlite_path, sql_query, timeout=3):
    """
    在给定的超时时间内执行 SQL，如果超时则返回 []

    :param sqlite_path: 数据库文件路径
    :param sql_query: 要执行的 SQL 查询
    :param timeout: 超时时间（秒）
    :return: 查询结果或 []
    """
    result = []
    thread_exception = [None]

    def run_query():
        nonlocal result
        try:
            conn = sqlite3.connect(sqlite_path)
            cursor = conn.cursor()
            cursor.execute(sql_query)
            result = cursor.fetchall()
            conn.close()
        except Exception as e:
            thread_exception[0] = e

    query_thread = threading.Thread(target=run_query)
    query_thread.start()
    query_thread.join(timeout)

    if query_thread.is_alive():
        # 超时，终止线程并返回 []
        raise TimeoutError(f"SQL 查询超时 ({timeout} 秒)")

    if thread_exception[0] is not None:
        raise thread_exception[0]

    return result



def copy_and_clear_database(sqlitePath, sqliteTmpDir):
    # Ensure the temporary directory exists
    if not os.path.exists(sqliteTmpDir):
        os.makedirs(sqliteTmpDir)
    else:
        # Clear all contents in the sqliteTmpDir
        for filename in os.listdir(sqliteTmpDir):
            file_path = os.path.join(sqliteTmpDir, filename)
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)

    # Determine the destination path for the copied SQLite file
    sqliteTmpPath = os.path.join(sqliteTmpDir, os.path.basename(sqlitePath))

    # Copy the original SQLite file to the temporary directory
    shutil.copy(sqlitePath, sqliteTmpPath)

    # Connect to the temporary database and clear all tables
    conn = sqlite3.connect(sqliteTmpPath)
    cursor = conn.cursor()

    # Get all table names and clear them
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table in tables:
        table_name = table[0]
        cursor.execute(f'DELETE FROM "{table_name}";')  # Clear all data
    conn.commit()

    return conn

def insert_test_data(conn, testList):
    cursor = conn.cursor()
    for insert_statement in testList:
        try:
            cursor.execute(insert_statement)  # 执行 INSERT 语句
        except Exception as e:
            print(f"insert_test_data Error executing statement: {insert_statement}")
        conn.commit()  # 提交所有成功的语句

import util
def generate_csv_from_database(conn, csvPath):
    cursor = conn.cursor()
    # Execute PRAGMA statement to get the database file path
    cursor.execute("PRAGMA database_list;")
    db_info = cursor.fetchall()
    # The first entry in the result is the main database file
    sqlite_path = db_info[0][2]

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [item[0] for item in cursor.fetchall()]
    for table_name in tables:
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        columns = [info[1] for info in cursor.fetchall()]
        csv_path = os.path.join(csvPath, f"{table_name.lower()}.csv")
        util.generate_csv(csv_path, sqlite_path, table_name, columns)


from collections import defaultdict


def find_most_frequent_answer(results):
    # Dictionary to store the frequency of each answer
    answer_frequency = defaultdict(int)
    for result in results:
        answer_frequency[result] = 0

    # Compare each result with all others
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            if codeResultEq(results[i], results[j]):  # Compare result[i] with result[j]
                # If they match, increase the frequency of the answer
                answer_frequency[results[i]] += 1
                answer_frequency[results[j]] += 1

    # Find the maximum frequency
    max_frequency = max(answer_frequency.values(), default=0)

    # Collect all answers with the maximum frequency
    most_frequent_answers = [answer for answer, freq in answer_frequency.items() if freq == max_frequency]

    return most_frequent_answers


def find_passing_code(predictedOriCodeList, testList, sqlitePath, sqliteTmpPath):
    # Dictionary to track the number of test cases each code passes
    code_pass_count = defaultdict(int)
    # Track the number of exceptions for each code
    code_exception_count = defaultdict(int)
    for code in predictedOriCodeList:
        code_pass_count[code] = 0
        code_exception_count[code] = 0

    # Set to track codes that never caused an exception
    codes_without_exceptions = set(predictedOriCodeList)
    # Iterate over each test case in testList
    for test_case in testList:
        # Copy the SQLite database and clear data
        conn = copy_and_clear_database(sqlitePath, sqliteTmpPath)

        # Insert test data into the temporary database
        insert_test_data(conn, test_case)

        # Generate CSV files from the database
        generate_csv_from_database(conn, sqliteTmpPath)
        conn.close()

        # Execute each code and capture the results
        results = []
        valid_codes = []  # Keep track of codes that are still valid

        for code_str in predictedOriCodeList:
            try:
                result = execute_code_and_capture_print(code_str)
                result = formatDataStr_set(result)
                # If result is empty or None, skip this code
                if not result or  not result:
                    continue
                results.append(result)
                valid_codes.append(code_str)
            except BaseException as e:
                # If an exception occurs, skip this code
                code_exception_count[code_str] += 1
                continue
        if not valid_codes:
            # If there are no valid codes left, continue to the next test case
            continue

        # Find the most frequent answer for this test case
        most_frequent_answers = find_most_frequent_answer(results)

        # Determine which codes passed this test case (those that match any of the most frequent answers)
        passing_codes = [valid_codes[i] for i, result in enumerate(results) if result in most_frequent_answers]

        # Increment the pass count for each passing code
        for code in passing_codes:
            code_pass_count[code] += 1

    # Find the maximum pass count
    max_pass_count = max(code_pass_count.values(), default=0)
    if max_pass_count > 0:
        # Select all codes with the maximum pass count
        best_codes = [code for code, count in code_pass_count.items() if count == max_pass_count]
    else:
        # If no code passed any test case, select codes with the minimum exception count
        min_exception_count = min(code_exception_count.values(), default=float('inf'))
        best_codes = [
            code for code, exception_count in code_exception_count.items() if exception_count == min_exception_count
        ]
        # best_codes= [random.choice(best_codes)]

    return best_codes, max_pass_count


def find_passing_code_returnALL(predictedOriCodeList, testList, sqlitePath, sqliteTmpPath):
    """
    这个函数是用于比较所有代码，并返回所有代码的通过次数、每个测试集合的结果差异数量
    :param predictedOriCodeList:
    :param testList:
    :param sqlitePath:
    :param sqliteTmpPath:
    :return:
    """
# Dictionary to track the number of test cases each code passes
    code_pass_count = defaultdict(int)
    # Track the number of exceptions for each code
    code_exception_count = defaultdict(int)
    # 增加测试用例区分个数
    testDiffResultCountList = []
    for code in predictedOriCodeList:
        code_pass_count[code] = 0
        code_exception_count[code] = 0

    # Set to track codes that never caused an exception
    codes_without_exceptions = set(predictedOriCodeList)
    # Iterate over each test case in testList
    for test_case in testList:
        # Copy the SQLite database and clear data
        conn = copy_and_clear_database(sqlitePath, sqliteTmpPath)

        # Insert test data into the temporary database
        insert_test_data(conn, test_case)

        # Generate CSV files from the database
        generate_csv_from_database(conn, sqliteTmpPath)
        conn.close()

        # Execute each code and capture the results
        results = []
        valid_codes = []  # Keep track of codes that are still valid

        for code_str in predictedOriCodeList:
            try:
                result = execute_code_and_capture_print(code_str)
                result = formatDataStr_set(result)
                # If result is empty or None, skip this code
                if not result or  not result:
                    continue
                results.append(result)
                valid_codes.append(code_str)
            except BaseException as e:
                # If an exception occurs, skip this code
                code_exception_count[code_str] += 1
                continue
        if not valid_codes:
            testDiffResultCountList.append(0)
            # If there are no valid codes left, continue to the next test case
            continue

        # Find the most frequent answer for this test case
        most_frequent_answers = find_most_frequent_answer(results)

        # Determine which codes passed this test case (those that match any of the most frequent answers)
        passing_codes = [valid_codes[i] for i, result in enumerate(results) if result in most_frequent_answers]
        testDiffResultCountList.append(len(set(results)))
        # Increment the pass count for each passing code
        for code in passing_codes:
            code_pass_count[code] += 1

    passCountList = [code_pass_count[code] for code in predictedOriCodeList]
    exceptionCountList = [code_exception_count[code] for code in predictedOriCodeList]
    return passCountList ,exceptionCountList, testDiffResultCountList

