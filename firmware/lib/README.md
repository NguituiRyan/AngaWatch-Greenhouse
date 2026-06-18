# Private libraries

PlatformIO automatically compiles any project-private libraries placed here as
`lib/<LibName>/src/...`. Use this for vendored or in-house drivers you do not want
to pull from the registry (e.g. a calibrated NPK register map, a custom leaf-wetness
conversion). Third-party registry libraries are declared in `platformio.ini`
(`lib_deps`) instead.

See https://docs.platformio.org/en/latest/librarymanager/
