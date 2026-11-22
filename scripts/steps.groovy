def runPython(String arguments) {
    if (isUnix()) {
        sh(label: 'NYC311 Python', script: 'exec "${PYTHON_BIN:-python3.12}" ' + arguments)
    } else {
        bat(label: 'NYC311 Python', script: '@echo off\r\nif defined PYTHON_BIN (\r\n  "%PYTHON_BIN%" ' + arguments + '\r\n) else (\r\n  py -3.12 ' + arguments + '\r\n)')
    }
}

return this
