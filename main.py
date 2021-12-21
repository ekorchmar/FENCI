# todo:
# After tech demo
# todo:
#  Credits in Main Menu and after beating Lvl4 Skirmish
#  Hall of fame for beating lvl4 arena
#  make ALL string constants come from language json
#  seeded random
#  Speedrun mode
#  split threads by Input+calculation // drawing OR try to draw less often after splitting input from drawing
#  try to update FPS_TICK by get_time

import base_class as b
import equipment as eq
import handler as hd
from primitive import *
import argparse
import cProfile
import pstats

msg = "Enable profiling with --profiling <filename> or -p <filename>. Other arguments will raise an Exception."

# Initialize arguments parsing:
parser = argparse.ArgumentParser()
parser.add_argument("-p", "--profiling", help="Enable profiling output to a specified filename")
args = parser.parse_args()


# Define the main loop:
def main():
    # Initiate material registry:
    b.Material.init()

    # Initiate sound:
    load_sound_profile(OPTIONS["sound"])

    # Initiate controls:
    b.MouseV.instantiate()

    # Log state to console:
    print(f"Loaded sounds from profile {SOUND_PROFILES[OPTIONS['sound']]}: "
          f"{', '.join(SOUND.keys()) or 'None'}")
    print()
    print(f"Spawnable monsters: {', '.join(b.Character.registry.keys()) or 'None'}")
    print(f"Droppable weapons: {', '.join(eq.Wielded.registry.keys()) or 'None'}")
    print(f"Droppable hats: {', '.join(eq.Hat.registry.keys()) or 'None'}")
    print()
    for tier in range(5):
        level = filter(lambda x: artifacts[x]["tier"] == tier, list(artifacts.keys()))
        print(f"Loaded artifacts at tier {tier}: {', '.join(level) or 'None'}")

    # Scene Handler to start:
    if PROGRESS["tutorial_completed"]:
        hd.SceneHandler.active = hd.MainMenuSceneHandler(web_prompt=False)
    else:
        hd.TutorialSceneHandler()

    while not hd.SceneHandler.active.completed:
        hd.SceneHandler.active.execute()

    pygame.quit()


if __name__ == "__main__":

    if args.profiling is None:
        # Simply run the loop:
        main()

    else:
        # If profiling is enabled, start profiling:
        with cProfile.Profile() as pr:
            main()

        stats = pstats.Stats(pr)
        stats.sort_stats(pstats.SortKey.TIME)
        stats.print_stats()
        stats.dump_stats(filename=args.profiling)
