// library for simple string modifications
package lib

// This function runs a test inside of a Jenkins stage
// NAME: Display name of the Stage, should describe the test
// CONDITION: true or false, determening whether the stage has to be run
// DIR: Directory in which the test is executed
// ENV_VARS: Array [] of environment variables needed for the test
// COMMAND: command that should be executed. It should be possible to use this exact
//          command to reproduce the test locally in the coresponding DIR
// TEXT_ON_SKIP: Information that is displayed if the test was skipped
def run(Map args) {
    stage(args.NAME) {
        if (args.CONDITION) {
            dir(args.DIR) {
                withEnv(args.ENV_VARS) {
                    sh(". /bauwelt/bin/bw-setup-jenkins-env ; " + args.COMMAND)
                }
            }
        } else {
            println(args.TEXT_ON_SKIP)
        }
    }
}

return this
