#!groovy

/// file: tests_helper.groovy

// execute tests, catch error and output log
def execute_test(Map config = [:]) {
    // update the default map content with the user provided config content
    // new key/value of provided map is automatically added to the defaultDict
    def defaultDict = [
        name: "",
        cmd: "",
        output_file: ""
    ] << config;

    stage("Run ${defaultDict.name}") {
        // catch any error, set stage + build result to failure,
        // but continue in order to execute the publishIssues function
        catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
            def cmd = defaultDict.cmd;
            if (defaultDict.output_file) {
                cmd += " 2>&1 | tee ${defaultDict.output_file}"
            }
            sh("""
                set -o pipefail
                ${cmd}
            """);
        }
    }
}

// create issues parser
// in case 'as_stage' is set false, the parser list will be returned
// otherwise a publish issue stage is created
def analyse_issues(result_check_type, result_check_file_pattern, as_stage=true) {
    def issues = [];
    def parserId = '';  // used for custom groovyScript parser

    switch (result_check_type) {
        case "BAZELFORMAT":
            parserId = 'bazel-format';
            update_custom_parser([
                id: parserId, // ID
                name: 'Bazel Format', // Name shown on left side menu
                regex: '(.*)\\s#\\s(reformat)$', // RegEx
                mapping: 'return builder.setFileName(matcher.group(1)).setMessage(matcher.group(2)).buildOptional()', // Mapping script
                example: "omd/packages/freetds/freetds_http.bzl # reformat"  // example log message
                //       |               1                     |  |   2   |
            ]);
            issues.add(scanForIssues(
                tool: groovyScript(
                    parserId: parserId,
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "BAZELLINT":
            parserId = 'bazel-lint';
            update_custom_parser([
                id: parserId, // ID
                name: 'Bazel Lint', // Name shown on left side menu
                regex: '(.*):(\\d+):(\\d+):(.*)', // RegEx
                mapping: 'return builder.setFileName(matcher.group(1)).setMessage(matcher.group(4)).setLineStart(Integer.parseInt(matcher.group(2))).setColumnStart(Integer.parseInt(matcher.group(3))).buildOptional()', // Mapping script
                example: "omd/packages/freetds/freetds_http.bzl:8:19: syntax error near build_file"  // example log message
                //       |               1                     |2|3 |             4               |
            ]);
            issues.add(scanForIssues(
                tool: groovyScript(
                    parserId: parserId,
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "CLANG":
            issues.add(scanForIssues(
                tool: clang(
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "CSSFORMAT":
            parserId = 'css-format';
            update_custom_parser([
                id: parserId, // ID
                name: 'CSS Format', // Name shown on left side menu
                regex: '^\\[warn\\]\\s(.*\\.(?:sc|c)ss)$', // RegEx
                mapping: 'return builder.setFileName(matcher.group(1)).buildOptional()', // Mapping script
                example: "[warn] web/htdocs/themes/facelift/scss/_bi.scss"  // example log message
                //       |      |          1                             |
            ]);
            issues.add(scanForIssues(
                tool: groovyScript(
                    parserId: parserId,
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "ESLINT":
            issues.add(scanForIssues(
                tool: esLint(
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "GCC":
            issues.add(scanForIssues(
                tool: gcc(
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "JUNIT":
            issues.add(scanForIssues(
                tool: junitParser(
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "MYPY":
            issues.add(scanForIssues(
                tool: myPy(
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "PYLINT":
            issues.add(scanForIssues(
                tool: pyLint(
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "SHELLCHECK":
            parserId = 'shellcheck';
            update_custom_parser([
                id: parserId, // ID
                name: 'Shellcheck', // Name shown on left side menu
                regex: '''(In)\\s(.*)\\s(.*)\\s(\\d*):\\n(.*)\\n(.*)(\\^-*\\^)\\s(\\w*\\d*)(?:\\:|\\s\\(\\w*\\)\\:)\\s(.*)''', // RegEx
                mapping: 'return builder.setFileName(matcher.group(2)).setCategory(matcher.group(8)).setMessage(matcher.group(9)).setLineStart(Integer.parseInt(matcher.group(4))).buildOptional()', // Mapping script
                example: """In ./enterprise/skel/etc/init.d/dcd line 14:
                . \"\$OMD_ROOT/.profile\"
                  ^------------------^ SC1091 (info): Not following: ./.profile: openBinaryFile: does not exist (No such file or directory)"""  // example log message
                // |1 |             2                 | 3  | 4 |
                // |         5        |
                // | 6 |      7       |  8   |  9   |  10                   |
            ]);
            issues.add(scanForIssues(
                tool: groovyScript(
                    parserId: parserId,
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "SHELLUNIT":
            parserId = 'shell-unit';
            update_custom_parser([
                id: parserId, // ID
                name: 'Shell Unittests', // Name shown on left side menu
                regex: '''(.*\\.sh)(.*)(ERROR)(.*\\(\\))(.*\\n)*(.*ASSERT.*)(.*\\n.*)*''', // RegEx
                mapping: 'return builder.setFileName(matcher.group(1)).setCategory(matcher.group(3)).setMessage(matcher.group(6)).buildOptional()', // Mapping script
                example: """tests/unit-shell/agents/test_set_up_path.shshunit2:ERROR test_set_up_path_already_in_path() returned non-zero return code.
                test_set_up_path_already_in_path
                ASSERT:expected:</foo:/usr/local/bin:/bar2> but was:</foo:/usr/local/bin:/bar>"""  // example log message
                // |                     1                             |  2   |  3  |             4                    |
                // |            5               |
                // |                          6                                               |
            ]);
            issues.add(scanForIssues(
                tool: groovyScript(
                    parserId: parserId,
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "TSJSBUILD":
            parserId = 'ts-build';
            update_custom_parser([
                id: parserId, // ID
                name: 'TS/JS build', // Name shown on left side menu
                regex: '(.*):\\s(.*):\\s(.*)\\s\\((\\d+):(\\d+)\\)', // RegEx
                mapping: 'return builder.setFileName(matcher.group(2)).setCategory(matcher.group(1)).setMessage(matcher.group(3)).setLineStart(Integer.parseInt(matcher.group(4))).setColumnStart(Integer.parseInt(matcher.group(5))).buildOptional()', // Mapping script
                example: "SyntaxError: web/htdocs/js/modules/dashboard.ts: Missing semicolon. (65:30)"  // example log message
                //       |     1     |                    2              |         3        | 4  |5 |
            ]);
            issues.add(scanForIssues(
                tool: groovyScript(
                    parserId: parserId,
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "TSJSFORMAT":
            parserId = 'js-format';
            update_custom_parser([
                id: parserId, // ID
                name: 'TS/JS Format', // Name shown on left side menu
                regex: '^\\[warn\\]\\s(.*\\.(?:j|t)s)$', // RegEx
                mapping: 'return builder.setFileName(matcher.group(2)).buildOptional()', // Mapping script
                example: "[warn] web/htdocs/js/modules/cbor_ext.js"  // example log message
                //        |  1  |             2                   |
            ]);
            issues.add(scanForIssues(
                tool: groovyScript(
                    parserId: parserId,
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        case "TSJSTYPES":
            parserId = 'ts-types';
            update_custom_parser([
                id: parserId, // ID
                name: 'TS/JS types', // Name shown on left side menu
                regex: '(.*\\..*(?:ts|js))\\((\\d+),(\\d+)\\):\\s(.*):\\s(.*)', // RegEx
                mapping: 'return builder.setFileName(matcher.group(1)).setCategory(matcher.group(4)).setMessage(matcher.group(5)).setLineStart(Integer.parseInt(matcher.group(2))).setColumnStart(Integer.parseInt(matcher.group(3))).buildOptional()', // Mapping script
                example: "web/htdocs/js/modules/dashboard.js(65,37): error TS1005: ',' expected.s"  // example log message
                //       |      1                           |2 | 3 |      4      |      5        |
            ]);
            issues.add(scanForIssues(
                tool: groovyScript(
                    parserId: parserId,
                    pattern: "${result_check_file_pattern}"
                )
            ));
            break;
        default:
            println("No tool defined for RESULT_CHECK_TYPE: ${result_check_type}");
            break;
    }

    if (as_stage) {
        analyse_issue_stages(issues);
    }
    else {
        return issues;
    }
}

// pusblish issues stage based on given issue parser(s)
def analyse_issue_stages(issues) {
    if (issues) {
        stage("Analyse Issues") {
            publishIssues(
                issues: issues,
                trendChartType: "TOOLS_ONLY",
                qualityGates: [[
                    threshold: 1,
                    type: "TOTAL",
                    unstable: false,
                ]],
            );
        }
    }
    else {
        println("WARNING: No issue parsers given");
    }
}

// update custom parser with new configs, existing parsers will be overwritten
def update_custom_parser(Map config = [:]) {
    // update the default map content with the user provided config content
    // new key/value of provided map is automatically added to the defaultDict
    def defaultDict = [
        id: "",
        name: "",
        regex: "",
        mapping: "",
        example: "",
    ] << config;

    def parser_config = io.jenkins.plugins.analysis.warnings.groovy.ParserConfiguration.getInstance();
    def existing_parsers = parser_config.getParsers();

    def newParser = new io.jenkins.plugins.analysis.warnings.groovy.GroovyParser(
        defaultDict.id,
        defaultDict.name,
        defaultDict.regex,
        defaultDict.mapping,
        defaultDict.example
    );

    if (parser_config.contains(defaultDict.id)) {
        print("${defaultDict.id} already defined, updating parser");
        existing_parsers[existing_parsers.indexOf(newParser)] = newParser;
        parser_config.setParsers(existing_parsers);
    }
    else {
        print("${defaultDict.id} undefined, adding parser");
        parser_config.setParsers(existing_parsers.plus(newParser));
    }
}

return this;
