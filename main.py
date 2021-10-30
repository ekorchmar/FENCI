# todo:
#  8 bit sounds for weapon and character collisions
#  Credits in Main Menu and after beating Lvl4 Skirmish
# After tech demo
# todo:
#  make ALL string constants come from language json
#  seeded random
#  Speedrun mode
#  split threads by Input+calculation // drawing OR try to draw less often after splitting input from drawing
#  try to update FPS_TICK by get_time

from scene import *

if __name__ == "__main__":
    # Initiate material registry:
    Material.init()
    print(f"Material physics:{', '.join(set(Material.registry[material].physics for material in Material.registry))}")

    # Initiate sound:
    load_sound_profile(OPTIONS["sound"])

    # Log state to console:
    print(f"Loaded sounds from profile {SOUND_PROFILES[OPTIONS['sound']]}: "
          f"{', '.join(SOUND.keys()) or 'None'}")
    print()
    print(f"Spawnable monsters: {', '.join(Character.registry.keys()) or 'None'}")
    print(f"Droppable weapons: {', '.join(Wielded.registry.keys()) or 'None'}")
    print(f"Droppable hats: {', '.join(Hat.registry.keys()) or 'None'}")
    print()
    for tier in range(5):
        level = filter(lambda x: artifacts[x]["tier"] == tier, list(artifacts.keys()))
        print(f"Loaded artifacts at tier {tier}: {', '.join(level) or 'None'}")

    # Scene Handler to start:
    # SceneHandler.active = SkirmishScenehandler(1)
    # SceneHandler.active = SceneHandler(1, [Orc], monster_total_cost=50, loot_drops=0, on_scren_enemies_value=(1, 1))
    SceneHandler.active = MainMenuSceneHandler()

    # Custom equipment (will not work in Main Menu)
    # SceneHandler.active.scene.player.equip(Sword(BASE_SIZE, tier_target=2), 'main_hand')
    # SceneHandler.active.scene.player.equip(Katar(BASE_SIZE, tier_target=2), 'off_hand')
    # SceneHandler.active.scene.log_weapons()

    while True:
        SceneHandler.active.execute()
        pygame.event.pump()
