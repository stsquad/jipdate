#!/usr/bin/env python

from __future__ import print_function
import json
import os
import re
import sys
import tempfile
from argparse import ArgumentParser
from jira import JIRA
from subprocess import call
import sys

# Sandbox server
server = 'https://dev-projects.linaro.org'

# Production server, comment out this in case you want to use the real server
#server = 'https://projects.linaro.org'

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def vprint(*args, **kwargs):
    if verbose:
        print(*args, file=sys.stdout, **kwargs)

def get_parser():
    parser = ArgumentParser(description='Script used to update comments in Jira')

    parser.add_argument('-q', required=False, action="store_true", \
            default=False, \
            help='Query Jira for issue(s) assigned to you')

    parser.add_argument('-e', required=False, action="store_true", \
            default=False, \
            help='Only include epics (no initiatives or stories). Used in combination \
            with "-c"')

    parser.add_argument('-f', '--file', required=False, action="store", \
            default=None, \
            help='file to use containing a status update(s)')

    parser.add_argument('-v', required=False, action="store_true", \
            default=False, \
            help='Output some verbose debugging info')

    parser.add_argument('-x', required=False, action="store_true", \
            default=False, \
            help='EXCLUDE stories from gathered Jira issues. Used in combination \
            with "-c"')

    parser.add_argument('--all', required=False, action="store_true", \
            default=False, \
            help='Load all Jira issues, not just the once marked in progress.')

    return parser

################################################################################

def get_my_name():
    n = os.environ['JIRA_USERNAME'].split("@")[0].title()
    return n.replace(".", " ")

################################################################################

def update_jira(jira, i, c):
    vprint("Updating Jira issue: %s with comment:" % i)
    vprint("-- 8< --------------------------------------------------------------------------")
    vprint("%s" % c)
    vprint("-- >8 --------------------------------------------------------------------------\n\n")
    jira.add_comment(i, c)

################################################################################

message_header = """Hi,

This is the status update from me for the last week.

Cheers!
"""

def get_jira_issues(jira, exclude_stories, epics_only, all_status, filename):
    issue_types = ["Epic"]
    if not epics_only:
        issue_types.append("Initiative")
        if not exclude_stories:
            issue_types.append("Story")
    issue_type = "issuetype in (%s)" % ", ".join(issue_types)

    status = "status in (\"In Progress\")"
    if all_status:
        status = "status not in (Resolved, Closed)"

    jql = "%s AND assignee = currentUser() AND %s" % (issue_type, status)
    vprint(jql)

    my_issues = jira.search_issues(jql)
    msg = message_header + get_my_name() + "\n\n"

    f = open_file(filename)
    filename = f.name

    f.write(msg)
    vprint("Found issue:")
    for issue in my_issues:
        vprint("%s : %s" % (issue, issue.fields.summary))
        f.write("[%s]\n" % issue)
        f.write("# Header: %s\n" % issue.fields.summary)
        f.write("# Type: %s\n" % issue.fields.issuetype)
        f.write("# Status: %s\n" % issue.fields.status)
        f.write("No updates since last week.\n\n")

    f.close()
    return filename

################################################################################
def should_update():
    while True:
        answer = raw_input("Sure you want to update Jira with the information " +
                           "above? [y/n] ").lower().strip()
        if answer in set(['y', 'n']):
            return answer
        else:
            print("Incorrect input: %s" % answer)

################################################################################
def open_editor(filename):
    if "EDITOR" in os.environ:
        editor = os.environ['EDITOR']
    elif "VISUAL" in os.environ:
        editor = os.environ['VISUAL']
    elif os.path.exists("/usr/bin/editor"):
        editor = "/usr/bin/editor"
    elif os.path.exists("/usr/bin/vim"):
        editor = "/usr/bin/vim"
    else:
        eprint("Could not load an editor.  Please define EDITOR or VISAUL")
        sys.exit()

    call([editor, filename])

def print_status(status):
    print("This is your status:")
    print("\n---\n")
    print("\n".join(l.strip() for l in status))

################################################################################
def parse_status_file(jira, filename):
    # Regexp to match Jira issue on a single line, i.e:
    # [SWG-28]
    # [LITE-32]
    # etc ...
    regex = r"^\[([A-Z]+-\d+)\]\n$"

    # Contains the status text, it could be a file or a status email
    status = ""

    with open(filename) as f:
        status = f.readlines()

    myissue = "";
    mycomment = "";

    # build list of {issue-key,comment} tuples found in status
    issue_comments = []
    for line in status:
        # New issue?
        match = re.search(regex, line)
        if match:
            myissue = match.group(1)
            issue_comments.append((myissue, ""))
        else:
            # Don't add lines with comments
            if (line[0] != "#" and issue_comments):
                (i,c) = issue_comments[-1]
                issue_comments[-1] = (i, c + line)

    print("These JIRA cards will be updated as follows:\n")
    for (idx,t) in enumerate(issue_comments):
        (issue,comment) = issue_comments[idx]

        # Strip beginning  and trailing blank lines
        comment = comment.strip()
        issue_comments[idx] = (issue, comment)
        print("[%s]\n  %s" % (issue, "\n  ".join(comment.splitlines())))
    print("")

    if should_update() == "n":
        print("No change, Jira was not updated!\n")
        print_status(status)
        sys.exit()

    # if we found something, let's update jira
    for (issue,comment) in issue_comments:
        update_jira(jira, issue, comment)

    print("Successfully updated your Jira tickets!\n")
    print_status(status)

def open_file(filename):
    vprint("filename: %s\n" % filename)
    if filename:
        return open(filename, "w")
    else:
        return tempfile.NamedTemporaryFile(delete=False)

################################################################################
def main(argv):
    global verbose

    parser = get_parser()
    args = parser.parse_args()

    verbose=args.v
    try:
        username = os.environ['JIRA_USERNAME']
        password = os.environ['JIRA_PASSWORD']
    except KeyError:
        eprint("Forgot to export JIRA_USERNAME and JIRA_PASSWORD?")
        sys.exit()

    credentials=(username, password)
    jira = JIRA(server, basic_auth=credentials)

    exclude_stories = args.x
    epics_only = args.e
    if args.x or args.e:
        if not args.q:
            eprint("Arguments '-x' and '-e' can only be used together with '-c'")
            sys.exit()

    if args.q:
        filename = get_jira_issues(jira, exclude_stories, epics_only, args.all, args.file)
    elif args.file is not None:
        filename = args.file
    else:
        eprint("No file provided and not in query mode\n")
        parser.print_help()
        sys.exit()

    open_editor(filename)
    parse_status_file(jira, filename)

if __name__ == "__main__":
        main(sys.argv)
