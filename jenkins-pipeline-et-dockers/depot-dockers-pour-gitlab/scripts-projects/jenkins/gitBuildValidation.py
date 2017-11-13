#!/usr/bin/python
#
# Description : Python script to validate if Jenkins need build the project
#               or ignore it
#
# Author : thomas.boutry@x3rus.com
# Licence : GPLv3
# TODO :
#   - Validation avec le Merge PAS juste le Push Request
#   - Ajouter les exclusions user et inclusion directory dans fic config
#   - Ajout parametre pour l'attente d'un processus de build
############################################################################

# Argument :
#   # Exclusion user
#   # Exclusion repertoire
#   # Disable validation jenkins build file in directory

###########
# Modules #


import argparse                                    # Process command line argument
from subprocess import Popen, PIPE, STDOUT         # Execute os command , here the git cmd
import re
import sys
import os
import pathlib
import configparser
import datetime


#########
# Class #

class gitBuildTriggerValidation():
    """
        Class to validate if Jenkins must perform the build or not , it's possible to exclude a user and include
        a directory or exlude one . The class will call git (os) command  to extracte git history.
        The class will call the Makefile in the directory
        Author : Thomas.boutry@x3rus.com
        Licence: GPLv3+
    """
    # CONST VARS , git parameters for the gi command ligne
    GIT_SHOW_ARGS_PRETTY = '--pretty="%aN;%ce %n%s%n%ct%nLists of commited files:"'
    GIT_SHOW_ARGS_NAME = '--name-only'
    TIMEOUT_WAIT_GIT_OPS = 20

    def __init__(self, userExclude=None, dirInclude=None, msgExclude=None, printInfo=False, dirExclude=None,
                 buildTimeout=60, configFileName="jenkins-build.cfg"):
        """ Init class , get user exclusion and directory include / exclude , set parameters """

        # ######################
        # process class argument
        if userExclude:
            self.lstUserExclude = userExclude.split(",")
        else:
            self.lstUserExclude = None

        if dirInclude:
            self.lstDirInclude = dirInclude.split(",")
        else:
            self.lstDirInclude = None

        if msgExclude:
            self.lstMsgExclude = msgExclude.split(",")
        else:
            self.lstMsgExclude = None

        if dirExclude:
            self.lstDirExclude = dirExclude.split(",")
        else:
            self.lstDirExclude = None

        if printInfo is True:
            self.verbose = True
        else:
            self.verbose = False

        # Set very old 1970-01-01
        self.lastCommitTimeStamp = datetime.datetime.fromtimestamp(int(1))

        # Define time allowed for ONE build
        self.buildTimeout = buildTimeout

        # Setup configue file name will be in earch Directory
        self.confFilePerDirectory = configFileName

        # Initialize Build Status Variable
        self.statusBuild = []

    # END init

    def getCommitHistoryAndValidate(self, commitNumber=None):
        """ Get Commit history since the commut Number in argument

            Extract all git commit information and performe validation for each
            return True Or False With list of ALL commit

            Arguments:
                commitNumer : Git commit number where to start analyse if not set check all commits (default None)

            Return:
                buidMustRun  : True or False , indicate if the build must be perform or not after creteria validation
                DirToProcess : List of directory to process
        """

        # Initialize variables
        DirToProcess = []
        buildMustRun = False
        commitTimeStamp = None

        # If not commit number is pass process every commit history
        if commitNumber is None:
            cmdOs_gitLogCmd = Popen(['git', 'log', '--pretty="%H"'], stdout=PIPE, stderr=STDOUT)
        else:
            ArgGitLog = str(commitNumber) + "..HEAD"  # from commitNumber to the last commit (head)
            cmdOs_gitLogCmd = Popen(['git', 'rev-list', ArgGitLog], stdout=PIPE, stderr=STDOUT)

        # Process every commit number
        for commitNum in cmdOs_gitLogCmd.stdout.readlines():
            commitNum_clean = commitNum.rstrip().strip(b'"')

            # Check if the commit meet creteria
            BuildthisCommit, lstDirForThisCommit, commitTimeStamp = self.validateCriteriaOnCommit(commitNum_clean)
            if BuildthisCommit is True:
                # extend list definition , append will create list in list
                DirToProcess.extend(lstDirForThisCommit)
                buildMustRun = BuildthisCommit
                d_commitTimeStamp = datetime.datetime.fromtimestamp(int(commitTimeStamp))
                if d_commitTimeStamp > self.lastCommitTimeStamp:
                    self.lastCommitTimeStamp = d_commitTimeStamp

        return buildMustRun, DirToProcess

    # END getCommitHistoryAndValidate

    def validateCriteriaOnCommit(self, commitNumber=None):
        """ Check if a commit meet criteria ( user , commit msg , ... )

            Arguments:
                commitNumer : Git commit number to validate of None process the last commit

            Return :
                buidMustRun  : True or False , indicate if the commit must be build.
                DirLst       : List of directory to process
                commitTimeStamp : Return commit TimeStamp processed
        """
        # By default we run the build
        buildMustRun = True
        DirLst = None

        # Extract git information with git command line
        if commitNumber is None:
            cmdOs_gitShowLastCmd = Popen(['git', 'show', self.GIT_SHOW_ARGS_PRETTY, self.GIT_SHOW_ARGS_NAME],
                                         stdout=PIPE, stderr=STDOUT)
        else:
            cmdOs_gitShowLastCmd = Popen(['git', 'show', self.GIT_SHOW_ARGS_PRETTY, self.GIT_SHOW_ARGS_NAME,
                                         commitNumber], stdout=PIPE, stderr=STDOUT)
        cmd_gitOutput = cmdOs_gitShowLastCmd.stdout.readlines()

        # cmd_gitOutput looks like
        # TODO ajouter un exemple de git_output

        # Perform validation ( User , message , list directory )
        if self.lstUserExclude:
            if not self.userExcludeNotCommited(cmd_gitOutput[0]):
                return False, DirLst, None
        if self.lstMsgExclude:
            if not self.excludedMsgNotInTheCommit(cmd_gitOutput[1]):
                return False, DirLst, None
        commitTimeStamp = cmd_gitOutput[2]
        if self.lstDirInclude:
            buildMustRun, DirLst = self.directoryToIncludeInCommit(cmd_gitOutput[4:], commitTimeStamp)

        # If in verbose mode print commit number AND directory
        if buildMustRun and self.verbose:
            print(str(commitNumber) + " : " + str(DirLst))

        # Return status and Directory list
        return buildMustRun, DirLst, commitTimeStamp

    # END validateCriteriaOnCommit

    def commitAfterDirBuildSuccess(self, DirectoryName, commitMsg, jenkinsInfo):
        """ Commit Files added , it's suppose to be only the jenkins-configuration files Ex:
                x3-webdav/jenkins-build.cfg to the git repository .

            If the build is a success Jenkins with the git publisher ( post-build) will push it to the srv

            Arguments:
                DirectoryName   : Name of the directory actually processed
                commitMsg       : Generic message for the commit
                jenkinsInfo     : Must contein jenkins info like build number, url , node name , ...

            Return:
                True  : If the commit work properly
                False : If any problem append
        """

        Msg2Commit = commitMsg + " ; " + jenkinsInfo
        # Commit config file TODO : Ajouter un critère de commit pour que ce soit pas obligatoire
        cmdOs_commitConfFile = Popen(['git', 'commit', '-m', Msg2Commit], stdout=PIPE, stderr=STDOUT)

        cmdOs_commitConfFile.wait(self.TIMEOUT_WAIT_GIT_OPS)

        if cmdOs_commitConfFile.returncode != 0:
            print("WARNING: Unable to commit config file for Directory : " + DirectoryName)
            return False

        return True

    # END commitAfterDirBuildSuccess

    def directoryToIncludeInCommit(self, gitLoglstFiles, commitTimeStamp=None):
        """ Check in the git log if the directory in the criteria self.lstDirInclude is present

            Arguments:
                gitLoglstFiles  : List of directory from the git commit log to process
                commitTimeStamp : TimeStamp of the commit this will give the option to check if
                                  the directory was already build succefully for this commit

            Return:
                FoundDir : True or False if a directory is found in the commit
                DirToInclude : Directory found and match in the commit message with self.lstDirInclude
        """

        FoundDir = False
        DirToInclude = []

        datetimeCurrentBuildValidation = datetime.datetime.fromtimestamp(int(commitTimeStamp))

        # If I found a match don't need continue with other entry
        for dirToInclude in self.lstDirInclude:
            for fileInCommit in gitLoglstFiles:
                if re.match(".*" + dirToInclude + ".*", str(fileInCommit)):
                    # Open config file in the Directory and check commit date was already build
                    # successfuly
                    if pathlib.Path(dirToInclude + "/" + self.confFilePerDirectory).is_file():
                        # Extract last git commit build with success
                        config = configparser.ConfigParser()
                        config.read(dirToInclude + "/" + self.confFilePerDirectory)

                        # Extract from config file last commit successfully build
                        str_lastCommitBuildSuccess = config['DEFAULT']['CommitDateBuildWithSuccess']
                        datetimeLastBuildSuccess = datetime.datetime.fromtimestamp(int(str_lastCommitBuildSuccess))

                        # Check if last buid success is less than current commit
                        if datetimeLastBuildSuccess < datetimeCurrentBuildValidation:
                            FoundDir = True
                            DirToInclude.append(dirToInclude)
                        # else:       # TODO voir pour ne pas faire un print mais mettre l'info dans le dictionnaire
                        #    print("Build already perform for  " + dirToInclude)

                    else:
                        # TODO supprimer le print
                        print("WARNING: Conf file not found : ", dirToInclude + "/" + self.confFilePerDirectory)
                        # Not config file so I don't know if it's done so I include it
                        FoundDir = True
                        DirToInclude.append(dirToInclude)

        return FoundDir, DirToInclude

    # END directoryToIncludeInCommit

    def excludedMsgNotInTheCommit(self, gitLogStringMsgCommit):
        """ Check in the git log the message if the commit must be exclude

            Arguments:
                gitLogStringMsgCommit : Message of the commit commit

            Return:
                True or False : True if the pattern is not found , False if it's found
                                My mind behind , True if the build must be perform and False if not :P
        """

        # If I found a match don't need continue with other entry
        for MsgToExclude in self.lstMsgExclude:
            if re.match(".*" + MsgToExclude + ".*", str(gitLogStringMsgCommit)):
                return False

        return True

    # END excludedMsgNotInTheCommit

    def userExcludeNotCommited(self, gitLogStringUser):
        """Check in the git log commit if the user match the regex

            Arguments:
                gitLogStringUser : User name to validate , today I manage only 1 user
                                   must look like : "Will Smith;will.smith@toto.com \n'

            Return:
                True or False : True if the pattern is not found , False if it's found
                                My mind behind , True if the build must be perform and False if not :P

            TODO : Be able to exclude a list of users
        """

        # If I found a match don't need continue with other entry
        for userToExclude in self.lstUserExclude:
            if re.match(".*" + userToExclude + ".*", str(gitLogStringUser)):
                return False

        return True

    # END userExcludeNotCommited

    def buildDirectory(self, dirToBuild):
        """ Perform build operation for directory so call MakeFile  with make command

            Arguments:
                dirToBuild : Directory to process the build , system will check if Makefile is present

            Return:
                True of False : if the build is a success, Warning if the directory don't contains Makfile
                                method return False

            TODO  : catch xception si timeout !!!
        """

        # Current Build status
        dirStatus = {'directory': dirToBuild, 'output': "", 'status': False}

        # Check if Makefile is in the Directoy
        if pathlib.Path(dirToBuild+"/Makefile").is_file():

            start_build_time = datetime.datetime.now()   # Get time before start build

            # Start make in the good directory ( -C .... )
            cmdOs_performMake = Popen(['make', '-C', dirToBuild], stdout=PIPE, stderr=STDOUT)

            # Wait the process finish to get return code
            cmdOs_performMake.wait(self.buildTimeout)

            end_build_time = datetime.datetime.now()      # Get time when build is done

            build_time = end_build_time - start_build_time      # Calculate time used

            # Check if the make success and feed dictionary with status
            if cmdOs_performMake.returncode == 0:
                # Upadte config file in directory if the build is a success
                self.updateDirConfFile(dirToBuild, self.lastCommitTimeStamp)
                dirStatus['status_msg'] = "SUCCESS: build " + dirToBuild + "Build time used : " + str(build_time)
                dirStatus['output'] = cmdOs_performMake.stdout
                dirStatus['status'] = True
            else:
                dirStatus['status_msg'] = "ERROR: build " + dirToBuild + "Build failed after : " + str(build_time)
                dirStatus['output'] = cmdOs_performMake.stdout
                dirStatus['status'] = False
        else:
            dirStatus['status_msg'] = "No Makefile available for : " + dirToBuild+"/Makefile"
            dirStatus['status'] = False

        # Append Current Status with global Build Status it will be use for summary
        self.statusBuild.append(dirStatus)

        # Return Build Status
        return dirStatus['status']

    # END buildDirectory

    # def updateDirConfFile(self, CommitTimeStampToSave=self.lastCommitTimeStamp):
    def updateDirConfFile(self, confDirectory, commitTimestampToSave):
        """ Update Commit timeStamp with the timeStamp of the last build success

            Arguments:
                confDirectory : Specifie where wich directory to change
                commitTimestampToSave : Specifie the new timestamp to save

            Return:
                True of False : Return information of the update if it's a success or not

        """
        # Create configParser File
        config = configparser.ConfigParser()
        configFullPath = confDirectory + "/" + self.confFilePerDirectory

        if pathlib.Path(configFullPath).is_file():
            # Extract last git commit build with success
            config.read(configFullPath)

        # convert datetime with timestamp as int not float and convert it as string :-/
        config['DEFAULT']['CommitDateBuildWithSuccess'] = str(int(commitTimestampToSave.timestamp()))

        # Write config file :
        with open(configFullPath, 'w') as configfile:
            config.write(configfile)

        # Commit config file TODO : Ajouter un critère de commit pour que ce soit pas obligatoire
        cmdOs_addConfFile = Popen(['git', 'add', configFullPath], stdout=PIPE, stderr=STDOUT)

        # TODO : Voir pour changer cette option
        cmdOs_addConfFile.wait(20)

        if cmdOs_addConfFile.returncode != 0:
            print("WARNING: Unable to add config file " + configFullPath)
            print(cmdOs_addConfFile.stdout.readlines())
            print("Return code : " + cmdOs_addConfFile.returncode)

    def printStatusBuild(self):
        """ Print build Status use self.statusBuild to show all information.
            Check if verbose mode is on or off
        """

        print(50*"=")
        for aBuildStatus in self.statusBuild:

            print(" Directory\t\t:\t\t" + aBuildStatus['directory'])
            print(" Status\t\t:\t\t" + str(aBuildStatus['status']))
            print(" Message\t\t:\t\t" + aBuildStatus['status_msg'])

            # If verbose mode is on show Make command output
            if self.verbose is True:
                print("\t\t" + 50*"#")
                for line in aBuildStatus['output']:
                    print("\t\t" + str(line))
                print("\t\t" + 50*"#")
                print(50*"=")

    # END printStatusBuild

    def isAllBuildSuccess(self):
        """ Return True if ALL build success otherwise return False """

        for aBuild in self.statusBuild:
            if aBuild['status'] is not True:
                return False

        return True

    # END isAllBuildSuccess

#########
# Main  #


if __name__ == '__main__':

    # Set default value for last commit processed with success
    lastCommitBuildSuccess = None

    # #######################
    # Command Line Arguments
    parser = argparse.ArgumentParser(description='Process git Push Request and \
                                    stop jenkins process or continue with task.')
    parser.add_argument('--build-timeout', '-b', type=int, help='Setup timeout for one build ', default=60)
    parser.add_argument('--conf', '-c', help='passe configue file default: jenkins-build.cfg',
                        default="jenkins-build.cfg")
    parser.add_argument('--exclude-user', '-u', help='Exclude users for \
                        a git commit , list of users separated with comma ; \
                        you can use regex ')
    parser.add_argument('--exclude-msg', '-m', help='Exclude build if specifique word in the commit')
    parser.add_argument('--include-dir', '-D', help='Include directory for jenkins \
                        build , list of directory separated with comma ; You can \
                        use regex', required=True)
    parser.add_argument('--test', '-t', action='store_true', help='Perform a dry run no build ', default=False)
    parser.add_argument('--verbose', '-v', action='store_true', help='Unable Verbose mode', default=False)

    args = parser.parse_args()

    # Get Jenkins Variables
    jenkinsInfo = os.environ.get('BUILD_TAG')

    # instance Class and Search build required
    app = gitBuildTriggerValidation(args.exclude_user, args.include_dir, args.exclude_msg, args.verbose, None,
                                    args.build_timeout, args.conf)
    b_mustRunBuild, lstDirectory = app.getCommitHistoryAndValidate(lastCommitBuildSuccess)

    # If Build must be perform process each directory
    if b_mustRunBuild:
        print("Build must RUN")
        if lstDirectory:
            if (args.test is True):
                print("Dry-run only enable , not performing Make")
            else:
                # it's not a dry-run so process every directory,
                # set(lstDirectory) remove duplicate entry of a directory
                for dir2Build in set(lstDirectory):
                    print("Processing : " + dir2Build)
                    buildStatus = app.buildDirectory(dir2Build)

                    if buildStatus is True:
                        # commit configuration file
                        # TODO : Ajouter une condition pour pas que ce soit obligatoire
                        commitMsg = "[Jenkins] ConfigFile after build for " + str(dir2Build)
                        app.commitAfterDirBuildSuccess(dir2Build, commitMsg, jenkinsInfo)

                app.printStatusBuild()

        # For Jenkins status
        if app.isAllBuildSuccess() is True:
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        print("NO Build to perform, creteria not meet")
        sys.exit(0)

    # Not suppose to go there but :D
    sys.exit(0)
