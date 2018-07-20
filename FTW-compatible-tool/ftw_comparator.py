# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import argparse
import os
import sys
import json
import csv
import httplib
import random
import string
import ftw
import pytest
import re
from ftw import errors

# Define const string
DUMMY_REQUEST_MARK_STR = 'WB_Dummy_Request_URI'

# Get one request from the request file.
# @param request_file:  The request filename, generated by ftw_generator. 
#                       Each request is seperated by a '\0'. Also used by WB.
# @return:              A request string.
def get_requests(request_filename):
    with open(request_filename, 'r') as request_file:
        request_cnt = 0
        request = None
        request_list = []
        while(request != ''):
            request = ''
            char = request_file.read(1)
            while(char!='\0'):
                if(char == ''):
                    break
                request = request + char
                char = request_file.read(1)
            # Every normal request is followed by a dummy request. We do not need to dealing with dummy requests.
            if request != '' and request_cnt%2 == 0:
                request_list.append(request)
            request_cnt += 1
    return request_list

# Get one response from the response file.
# @param response_file: The response filename, generated by WB. 
#                       Each response is following a number, indicates the length of the response.
# @return:              A response string.
def get_responses(response_filename):
    with open(response_filename, 'r') as response_file:
        response = None
        response_cnt = 0
        response_list = []
        while(response != ''):
            # In each iteration, read a response
            response = ''
            length = ''
            # Read a number, this indicate the length of this reponse
            while (1):
                char = response_file.read(1)
                if(char == ''):
                    break
                elif (char >= '0') and (char <= '9'):
                    length += char
                elif length == '':
                    # There are no content any more
                    continue
                else:
                    break
            if length!='':
                length = int(length)
            if length == 0 or length == '':
                continue
            response = response_file.read(length)
            # Every normal request is followed by a dummy request. We do not need to dealing with responses of those dummy request.
            if response_cnt % 2 == 0:
                response_list.append(response)
            response_cnt = response_cnt + 1
        response_cnt = (response_cnt+1)/2
    return response_list

# Init the check status of log_contain and no_log_contain for all requests.
# @param conditions_dict_list:      The list of all requests' conditions. 
#                                   Each entry of the list is a diction, contains the conditions of a request.
# @param log_contains_ok_list:      The list of the log_contain check status for all requests.
# @param no_log_contains_ok_list:   The list of the no_log_contain check status for all requests.
def init_log_contains_status(conditions_dict_list, log_contains_ok_list, no_log_contains_ok_list):
    for index in range(0,len(conditions_dict_list)):
        diction = conditions_dict_list[index]
        if 'log_contains' in diction:
            log_contains_ok_list.append(False)
        else:
            log_contains_ok_list.append(True)
        no_log_contains_ok_list.append(True)

# Conduct the check for log_contains and no_log_contains.
# @param conditions_dict_list:      The list of all requests' conditions. 
#                                   Each entry of the list is a diction, contains the conditions of a request.
# @param log_contains_ok_list:      The list of the log_contain check status for all requests.
# @param no_log_contains_ok_list:   The list of the no_log_contain check status for all requests.
# @param log_filename:          The server's log filename.
def check_log_contains(conditions_dict_list, log_contains_ok_list, no_log_contains_ok_list, log_filename):
    global DUMMY_REQUEST_MARK_STR
    request_cnt = 0
    with open(log_filename, 'r') as log_file:
        for line in log_file:
            if DUMMY_REQUEST_MARK_STR in line:
                request_cnt += 1
                continue
            diction = conditions_dict_list[request_cnt]
            if 'log_contains' in diction:
                contain_content = diction['log_contains']
                if contain_content == '':
                    log_contains_ok_list[request_cnt] = True
                else:
                    pattern = re.compile(contain_content)
                    match = pattern.search(line)
                    if match:
                        log_contains_ok_list[request_cnt] = True
            
            if 'no_log_contains' in diction:
                contain_content = diction['no_log_contains']
                if contain_content == '':
                    no_log_contains_ok_list[request_cnt] = False
                else:
                    pattern = re.compile(contain_content)
                    match = pattern.search(line)
                    if match:
                        no_log_contains_ok_list[request_cnt] = False

# Build a structured response object from a given response string.
# Then check the expect_error condition.
# @param http_ua:           The empty response structure, generated by FTW library. Used to build the response object.
# @param raw_response:      The response string.
# @param condition_diction: The diction contains all conditions of this request.
# @return:                  The pair of expect_error check status, and the error string.
def build_response_and_check_error(condition_diction, http_ua, raw_response):
    error_OK = True
    error_catch = False
    error_str = ''
    try:
        http_ua.response_object = ftw.http.HttpResponse(raw_response,http_ua)
    except errors.TestError as err:
        error_catch = True
        if 'expect_error' in condition_diction:
            if str(condition_diction['expect_error']) == 'False':
                error_str = 'Caught an error but the yaml file expect no error:\n' + str(err)
                error_OK = False
            elif str(condition_diction['expect_error']) == 'True':
                error_OK = True
            else:
                pattern = re.compile(condition_diction['expect_error'])
                match = pattern.search(raw_response)
                if match:
                    error_OK = True
                else:
                    error_OK = False
        else:#no expect_error but catch error
            error_str = 'Caught an unexpected error:\n' + str(err)
            error_OK = False
    if not error_catch:
        if 'expect_error' in condition_diction:
            if str(condition_diction['expect_error']) == 'False':
                error_OK = True
            else:
                error_str = 'Expect an error but did not catch'
                error_OK = False
    return error_OK, error_str

# Check the response status(return code).
# @param condition_diction: The diction contains all conditions of this request.
# @param http_ua:           The empty response structure, generated by FTW library.
def check_response_status(condition_diction, http_ua):
    if 'status' in condition_diction:
        if condition_diction['status']!='':
            if http_ua.response_object!=None:
                pattern = re.compile(str(condition_diction['status']))
                match = pattern.search(str(http_ua.response_object.status))
                if match:
                    status_ok = True
                else:
                    status_ok = False
            else:
                status_ok = False
        else:
            status_ok = True
    else: 
        status_ok = True
    return status_ok

# Print the brief fail message in standard output. Then generate detailed information in string.
# @param condition_diction: The diction contains all conditions of this request.
# @param index_str:         The index of the request (in string format).
# @param error_ok:          The check result of the expect_error condition.
# @param log_contains_ok:   The check result of the log_contains condition.
# @param no_log_contains_ok:The check result of the no_log_contains condition.
# @param status_ok:         The check result of the status contidion.
# @param response_object:   The structured response object. Generated by FTW library. 
#                           Used to get the response's status(return code).
# @param error_str:         The description of the expect_error checking.
# @return:                  The detailed fail information string.
def output_fail_message(condition_diction, index_str, error_ok, log_contains_ok, no_log_contains_ok, status_ok, response_object, error_str):
    fail_msg = ''
    # Change the color to red
    print('\033[1;31;40m')
    buf =  "\n=====ASSERT FAILED: \"" + condition_diction['test_title'] + "\" Index: " + index_str +"====="
    print(buf)
    fail_msg += buf + '\n'
    if not error_ok:
        buf = error_str
        print(buf)
        fail_msg += buf + '\n'
    if not log_contains_ok:
        buf = 'Log_contains check error. Log_contains condition = ' + condition_diction['log_contains']
        print(buf)
        fail_msg += buf + '\n'
    if not no_log_contains_ok:
        buf = 'No_log_contains check error. No_log_contains condition = ' + condition_diction['no_log_contains']
        print(buf)
        fail_msg += buf + '\n'
    if not status_ok:
        buf = 'Expected Response Status: ' + str(condition_diction['status'])
        print(buf)
        fail_msg += buf + '\n'
        if response_object!= None:
            buf = 'Actual Response Status: ' + str(response_object.status)
        else:
            buf = 'Actual there is no status!'
        print(buf)
        fail_msg += buf + '\n'

    #Change the color to default
    print('\033[0m')
    return fail_msg

# The main function to do all check operations and save log into output files.
# @param conditions_dict_list:  The list of all requests' conditions. 
#                               Each entry of the list is a diction, contains the conditions of a request.
# @param raw_yaml_dict:         The diction which saves all raw YAML code. Used to generate log.
#                               The key of a dict element is the test title.
#                               The value of a dict element is the raw YAML code string.
# @param request_list:          The list of all raw request string.
# @param response_list:         The list of all raw response string.
# @param log_filename:          The server's log filename.
# @param output_filename:       The file's name to save compare result.
# @param output_json_filename:  The json file's name to save compare result. Used by ftw_log_searcher.
def conduct_compare(conditions_dict_list, raw_yaml_dict, request_list, response_list, log_filename, output_filename, output_json_filename):
    log_contains_ok_list = []
    no_log_contains_ok_list = []
    fail_msg_dict = {}
    
    init_log_contains_status(conditions_dict_list,log_contains_ok_list, no_log_contains_ok_list)
    #check the log_contains
    check_log_contains(conditions_dict_list, log_contains_ok_list, no_log_contains_ok_list, log_filename)
    
    with open(output_filename, 'wb') as output_file, open(output_json_filename, 'wb') as output_json_file:
        #check the status and output
        http_ua = ftw.http.HttpUA()
        fail_cnt = 0
        error_str = ''
        for index in range(0, len(request_list)):
            if index >= len(response_list):
                print('The number of response is less then requests!')
                return
            index_str = str(index)
            diction = conditions_dict_list[index]
            
            log_ok = log_contains_ok_list[index] and no_log_contains_ok_list[index]
            #TODO handle the excepted error
            error_ok, error_str = build_response_and_check_error(diction, http_ua, response_list[index])
            status_ok = check_response_status(diction, http_ua)
            #output
            if log_ok and status_ok and error_ok:
                buf = "\n=====ASSERT PASSED: \"" + diction['test_title'] + "\"; Index: " + index_str + '=====\n'
                if output_file!=None:
                    output_file.write(buf)
                log_msg = buf
            else:
                fail_cnt = fail_cnt + 1
                buf = output_fail_message(diction, index_str, error_ok, log_contains_ok_list[index], no_log_contains_ok_list[index], status_ok, http_ua.response_object, error_str)
                if output_file!=None:
                    output_file.write(buf)
                log_msg = buf
            if output_file!=None:
                buf =  'The raw yaml is: \n'
                buf +=(raw_yaml_dict[diction['test_title']] + '\n')
                buf += 'The request package is:\n'
                buf +=(request_list[index] + '\n\n')
                buf += 'The response package is:\n'
                buf +=(response_list[index] + '\n')
                output_file.write(buf)
                log_msg += buf
            fail_msg_dict[str(diction['test_title'])] = log_msg
        print('\033[1;33;40m')
        print('***************************Result Overview********************************')
        print('Number of total   requests: ' + str(len(request_list)))
        print('Number of unmatch requests: ' + str(fail_cnt))
        print('\033[0m')
        json.dump(fail_msg_dict, output_json_file, ensure_ascii=False)

# Check whether those files can be opened successfully
# @param input_filename_list:  the list of input filename.
# @param output_filename_list: the list of output filename.
def check_file_operation(input_filename_list, output_filename_list):
    #check output_request
    for filename in input_filename_list:
        try:
            fd = open(filename,'rb')
        except IOError:
            print('Can not open input file ' + filename)
            return False
        else:
            fd.close()
    
    for filename in output_filename_list:
        try:
            fd = open(filename,'wb')
        except IOError:
            print('Can not open file ' + filename)
            return False
        else:
            fd.close()

    return True

# @param input_request_filename:    The request package file generated by ftw_generator.
# @param input_response_filename:   The response file generated by WB.
# @param input_raw_yaml_filename:   The raw yaml diction file generated by ftw_generator.
# @param input_server_log_filename: The server's log file.
# @param input_conditions_filename: The request check condition file generated by ftw_generator.
# @param output_filename:           The file to save compare result.
# @param output_json_filename:      The file to save compare result in json format. Used by ftw_log_searcher.
def ftw_comparator( input_request_filename, 
                    input_response_filename, 
                    input_raw_yaml_filename, 
                    input_server_log_filename, 
                    input_conditions_filename,
                    output_filename,
                    output_json_filename
                    ):
    input_filename_list = { input_request_filename, 
                            input_response_filename, 
                            input_raw_yaml_filename, 
                            input_server_log_filename, 
                            input_conditions_filename}
    output_filename_list = {output_filename,
                            output_json_filename}
    if check_file_operation(input_filename_list,output_filename_list) != True:
        exit()
    #open the files
    if input_server_log_filename == '':
        print('Need to specify a log file!')
        return
    #Requests with log_not_contain or no log_contains flag, mark as pass at first
    #Requests with log_contains, mark as fail at first
    request_list = []
    response_list = []
    conditions_dict_list = []
    raw_yaml_dict = {}

    with open(input_conditions_filename, 'rb') as input_conditions_file:
        for line in input_conditions_file:
            conditions_dict_list.append(json.loads(line))

    with open(input_raw_yaml_filename, 'rb') as input_raw_yaml_file:
        for line in input_raw_yaml_file:
            raw_yaml_dict = json.loads(line)

    response_list = get_responses(input_response_filename)
    request_list = get_requests(input_request_filename)

    if len(response_list) != len(request_list):
        print('[WARNING]The number of requests and responses does not match!')
        print('The number of requests is' + str(len(request_list)))
        print('The number of responses is' + str(len(response_list)))

    conduct_compare(conditions_dict_list, raw_yaml_dict, request_list, response_list, input_server_log_filename, output_filename, output_json_filename)

    print('DONE!')

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input_request_file', '-q', 
                        help = 'The request package file generated by ftw_generator', 
                        default = 'temp_requests.dat')
    parser.add_argument('--input_response_file', '-r', 
                        help = 'The response file generated by WB', 
                        default = 'temp_responses.dat')
    parser.add_argument('--input_raw_yaml_file', '-y', 
                        help = 'The raw_yaml file generated by ftw_generator', 
                        default = 'temp_raw_yaml.dat')
    parser.add_argument('--input_server_log', '-L', 
                        help = 'The server\'s log file', 
                        required = True)
    parser.add_argument('--input_conditions_file', '-c', 
                        help = 'The response file generated by WB', 
                        default = 'temp_conditions.dat')
    parser.add_argument('--output_result', '-o', 
                        help = 'The file to save compare result', 
                        default = 'comp_output.dat')
    parser.add_argument('--output_result_json', '-j', 
                        help = 'The json file to save compare result, used by log sercher', 
                        default = 'comp_output.dat.json')
    args=parser.parse_args()
    ftw_comparator(args.input_request_file, args.input_response_file, args.input_raw_yaml_file, args.input_server_log,
                        args.input_conditions_file, args.output_result, args.output_result_json)
