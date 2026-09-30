# Karotto for Home Assistant

A native Home Assistant integration for a [karotto](https://github.com/maxkueng/karotto)
server, the self-hosted habit tracker with Habitica's mechanics and none of
the game. It talks to the same API the web and Android clients use and
listens to the server's event stream, so a change made on the phone shows up
in Home Assistant within a second without polling.

## What you get

One device per karotto account with:

| Entity | What |
|---|---|
| `todo.<account>_to_dos` | Your to-dos as a native to-do list. Add, rename, describe, set a due date, reorder, check off, delete. Completed to-dos appear in the list's completed section until the server prunes them. |
| `todo.<account>_dailies` | Today's due dailies. Checking one off runs the day rollover first, then scores it, so a completion after midnight lands on the right day. |
| `sensor.<account>_dailies_remaining` | Due dailies not yet done today. Attribute `tasks` lists their titles. |
| `sensor.<account>_dailies_completed` | Due dailies done today. |
| `sensor.<account>_open_to_dos` | Uncompleted to-dos. |
| `sensor.<account>_to_dos_due` | Uncompleted to-dos due today or overdue, in the account's time zone. |
| `sensor.<account>_last_rollover` | When the last day rollover ran. |
| `binary_sensor.<account>_rollover_pending` | On when a rollover is due and no client has run it yet. |

Actions (services):

| Action | What |
|---|---|
| `karotto.score` | Score a task by alias or ID. `direction` up completes a daily or to-do or counts a positive habit click, down does the reverse. `rollover` (default on) runs the day rollover first. Returns the updated task. |
| `karotto.run_rollover` | Run the day rollover if one is pending. Returns `ran` and `days_missed`. |
| `karotto.add_task` | Create a habit, daily or to-do. Returns the new task. |

The native `todo.*` actions (`todo.add_item`, `todo.update_item`,
`todo.remove_item`, `todo.get_items`) work on both lists.

## Install

### HACS

Add `https://github.com/maxkueng/karotto-ha-integration` as a custom
repository of type Integration, then download Karotto and restart Home
Assistant.

### Manual

Copy `custom_components/karotto` into `<config>/custom_components/` on the
Home Assistant host and restart.

## Configure

Settings → Devices & services → Add integration → Karotto. Enter the server
URL, username and password. The integration exchanges them for a long-lived API
token named "Home Assistant" and stores only the token; the password is
discarded. Revoke the token from karotto's Settings → API Tokens to lock the
integration out; it will then ask to sign in again.

Home Assistant must be able to reach the server's URL, the same one the web
app uses. Plain `http://` works on a trusted network.

## Example: tick a daily from an automation

```yaml
triggers:
  - trigger: state
    entity_id: input_boolean.shower_active
    from: "on"
    to: "off"
actions:
  - action: karotto.score
    data:
      task: shower
```

`shower` is the daily's alias, set in the task editor under Advanced Settings.

## Example: show today's dailies on a dashboard

```yaml
type: todo-list
entity: todo.karotto_max_dailies
```

## How it stays current

The integration opens the server's Server-Sent Events stream and applies task,
order and user changes as they arrive. It also refetches everything every ten
minutes and after every reconnect, so a dropped stream or a day rollover run by
another client is picked up without a restart.

## Reaching a server over Tailscale

Not required; any network path to the server works. If the server is only on
your tailnet, Home Assistant has to be on it too, and on Home Assistant OS
the Supervisor has to resolve the `*.ts.net` name. With the Tailscale app
installed, point the Supervisor's DNS at the tailnet resolver once:

```sh
ha dns options --servers dns://100.100.100.100
```

## Development

Plain Python with no dependencies beyond Home Assistant. Tests run against a
real Home Assistant core:

```sh
python -m venv .venv
.venv/bin/pip install homeassistant pytest-homeassistant-custom-component ruff
.venv/bin/pytest
.venv/bin/ruff check custom_components tests
```

## License

GNU General Public License v3.0, the same as karotto. See `LICENSE`.
