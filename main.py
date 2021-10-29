# todo:
#  Sound system
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

# Initiate material registry:
Material.init()

print(f"Spawnable monsters: {', '.join(Character.registry.keys()) or 'None'}")
print(f"Droppable weapons: {', '.join(Wielded.registry.keys()) or 'None'}")
print(f"Droppable hats: {', '.join(Hat.registry.keys()) or 'None'}")
for tier in range(5):
    level = filter(lambda x: artifacts[x]["tier"] == tier, list(artifacts.keys()))
    print(f"Loaded artifacts at tier {tier}: {', '.join(level) or 'None'}")

# SceneHandler.active = SceneHandler(1, [Goblin, Orc], [5, 1])
# SceneHandler.active = SceneHandler(1, [Orc], monster_total_cost=50, loot_drops=0, on_scren_enemies_value=(1, 1))
SceneHandler.active = MainMenuSceneHandler()
# SceneHandler.active.scene.player.equip(Sword(BASE_SIZE, tier_target=2), 'main_hand')
# SceneHandler.active.scene.player.equip(Katar(BASE_SIZE, tier_target=2), 'off_hand')
# SceneHandler.active.scene.log_weapons()

if __name__ == "__main__":
    while True:
        SceneHandler.active.execute()
