"""Filter stored commands as asRemoveUnusedfromBuildPose (8084–8121).

These are saved pose strings, not instructions to execute. Keep the source's
last/penultimate-token rule, including its whole-command dot test.
"""


def original_build_pose_commands(text, exists):
    result=[]
    for command in text.split(';'):
        tokens=command.split()
        if not tokens:
            continue
        offset=-2 if '.' in command else -1
        if len(tokens)<abs(offset):
            continue
        if exists(tokens[offset]):
            result.append(command+';')
    return ''.join(result)
