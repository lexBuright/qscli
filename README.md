# qscli - A quantified-self command-line interface

A collection of low-level and high-level tools to collect, store, and interact with information about yourself.

# Principles

- Where possible, small command-line tools should be created for general, quantified self-type tools; these low-level tools will be exec'ed by higher-level tools
- This framework needs flexibility: no backwards-compatibility is guaranteed. That said, the low-level tools are less likely to change than the high-level tools

# Scope

- This library does not concern itself with graphical tools.
- Though some tools may carry out a limited amount of analysis, particularly those related to gamification (or rather scorification), this is not the aim of this library.

# Low-level tools

- `qscount` - A very feature-complete tool for counting things
- `qswatch` - A very feature-complete stopwatch, supporting multiple simultaneous clocks. Has certain overlaps with `timetrap`
- `qsscore` - A tool for keeping track of high scores, telling you statistics about them, and otherwise gamifying activities
- `qsprogress` - A tool to provide feedback about progress through a task
- `qsprompt` - A tool to prompt for data in a human-friendly way; designed as a high-level version of `zenity`

Some of these tools end up having fairly similar data models, e.g. `qscount` and `qsscore`. This is to be expected: the value that these tools provide is specific tooling around the data structures.

# High-level tools

These are tools designed and used for real world tasks. They will tend to be "balls-of-mud" with strange edge-cases, and case-specific logic that is suitable for one purpose; They are likely to have bugs; may well not be completely implemented; and are liable to change radically.

However, one hopes they will be valuable for: illustrating how low-level tools can be used; identifying other low-level tools that should exist, and how the existing ones should be modified; actually doing real world thigns.

##  `qsexercise` - A tool to keep track of exercise while exercising, and provide feedback.

This was designed to be used via `libnotify` and keybindings from your window manager.

This has features to
- Count reps, comparing the number of reps between days.
- Compare the amount of exercise does one day to previous days
- Keep track of speeds of a treadmill over a period of time, deriving statistics from this curve and comparing it to similar curves- Keep track of endurance exercise (e.g. how long can you run at 13 km/h for) and compare how they change over time
- Flatten all the exercises you do in a single day down to one number

The key differentiators of this tool compared to similar web- or phone-based equivalents is:

- Easy hackability: hacking on a phone is hard, using a tool on a system that allows programming encourages people to make changse
- Real-time feedback
- Easy real-time entry. This is largely achieved through the use of a keyboard and avoiding android
- Proper access to an open source community. There *is* an open source community for phone apps (e.g. Fdroid), but it is not nearly as developed as the community for more general-purpose operating systems. Whenever creating an open source tool there is a degree of throwing a great deal of your time and effort into the ether. There is a certain risk that no one will use your code and it will merely be forgotten. This risk (and the amount of effort involved) is reduced by creating desktop tools.

The cost of these differences is a massively reduced user base, and having to use a real non-phone computer when exercising.  However,  one hopes that this is at least a *useful* and unique tool for a specific subset of the population.
