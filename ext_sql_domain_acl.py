#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Squid3 external ACL helper script to check if an authenticated user is allowed
# to access a certain domain or not

import psycopg2
from urllib.parse import urlparse
from sys import stdin, stdout
import argparse
from gc import collect


class DomainAccessControllerOnPostgreSql(object):
    def __init__(self, db_host, db_name, db_user, db_passwd, statement):
        self.connection = None
        self.db_host = db_host
        self.db_name = db_name
        self.db_user = db_user
        self.db_passwd = db_passwd
        self.prepared_statement = statement
        self.prepared_cursor = None
        self.error_string = None

    def open_db_connection_if_closed(self):
        if self.connection is None:
            db_connect_string = "host='{:s}' dbname='{:s}' user='{:s}' password='{:s}'".format(self.db_host, self.db_name, self.db_user, self.db_passwd)
            try:
                self.connection = psycopg2.connect(db_connect_string)
            except:
                self.error_string = "ERR Unable to connect to the database"
                self.connection = None # is this necessary? Just to be sure?
                return False
            return True
        else:
            return True

    def prepare_statement_if_not_already(self):
        if self.prepared_cursor is None:
            try:
                self.prepared_cursor = self.connection.cursor()
            except:
                self.error_string = "ERR Unable to create cursor"
                return False
            try:
                self.prepared_cursor.execute(self.prepared_statement)
            except:
                self.error_string = "ERR Unable to prepare statement"
                return False
            return True
        else:
            return True
    
    def close_db_connection_if_open(self):
        if self.connection is not None:
            try:
                self.prepared_cursor.close()
            except:
                self.error_string = "ERR Unable to close prepared cursor"
                self.prepared_cursor = None
                return False
            try:
                self.connection.close()
            except:
                self.error_string = "ERR Unable to close connection"
                self.connection = None
                return False
            return True
        else:
            return True

    def is_user_allowed_to_domain(self, username, domain):
        try:
            execute_statement = "EXECUTE user_domain_select (%s, %s);"
            self.prepared_cursor.execute(execute_statement, (username, domain))
        except:
            self.error_string = "ERR Unable to execute prepared statement"
            return False
        row = self.prepared_cursor.fetchone()
        if row is not None:
            # The domain is in the blacklist for this user
            self.error_string = "ERR User is not allowed to this domain"
            return False
        else:
            # User is allowed
            # self.error_string = "OK" # Tags?
            return True


def extract_domain_from_url(url):
    # Thanks to: http://stackoverflow.com/a/21564306/5292928
    parse_result = urlparse(url) # From urllib.parse
    if parse_result.netloc != '':
        return parse_result.netloc
    else:
        # Probably happens if the url has no protocol
        # example: "facebook.com/messages/something.html"
        return parse_result.path.split('/', 1)[0]

def extract_domain_and_username_from_line(line):
    # The line is formatted as "URL username"
    # Example: "https://www.facebook.com/index.html?var=2 johndoe"
    url, username = line.strip().split(' ', 1)
    return extract_domain_from_url(url), username

def cycle_over_stdin_lines(controller):
    collect() # Garbage collection to reduce memory before starting
    while True:
        line = stdin.readline()
        if not line:
            # EOF
            break
        if controller.open_db_connection_if_closed() == False:
            stdout.write(controller.error_string + "\n")
            stdout.flush()
            continue
        if controller.prepare_statement_if_not_already() == False:
            stdout.write(controller.error_string + "\n")
            stdout.flush()
            continue
        domain, username = extract_domain_and_username_from_line(line)
        if controller.is_user_allowed_to_domain(username, domain):
            stdout.write("OK\n")
            stdout.flush()
        else:
            stdout.write(controller.error_string + "\n")
            stdout.flush()

def parse_command_line_arguments():
    this_program_description = """\
Squid3 external ACL helper script to check if an authenticated user
is allowed to access a certain domain or not"""
    parser = argparse.ArgumentParser(description = this_program_description,
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--db-user",
                        default = "squid",
                        help = "User for database access")
    parser.add_argument("--db-password",
                        default = "squidpostgresqlpw",
                        help = "Clear text password for database access")
    parser.add_argument("--db-host",
                        default = "localhost",
                        help = "Host of the database as DNS name or IP address")
    parser.add_argument("--db-name",
                        default = "squid",
                        help = "Name of the database to connect to")
    parser.add_argument("--db-table",
                        default = "incrementalproxy.vw_domains_per_user",
                        help = "Name of the table to select usernames and domains from")
    parser.add_argument("--col-domain",
                        default = "domain",
                        help = "Name of the column with the domains")
    parser.add_argument("--col-username",
                        default = "username",
                        help = "Name of the column with the usernames")
    arguments_dict = parser.parse_args()
    return arguments_dict

def main():
    args = parse_command_line_arguments()
    prepared_statement = "PREPARE user_domain_select (text, text) AS SELECT TRUE FROM {:s} WHERE {:s} = $1 AND $2 LIKE {:s};".format(args.db_table, args.col_username, args.col_domain)
    controller = DomainAccessControllerOnPostgreSql(args.db_host, args.db_name, args.db_user, args.db_password, prepared_statement)
    cycle_over_stdin_lines(controller)
    if controller.close_db_connection_if_open() == False:
        stdout.write(controller.error_string + "\n")
        stdout.flush()

if __name__ == "__main__":
    main()