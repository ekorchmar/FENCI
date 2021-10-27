# todo:
#  starting equipment choice dialogue
#  placeholder Nexuiz music
# After tech demo
# todo:
#  make ALL string constants come from language json
#  seeded random
#  Sound system
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
# SceneHandler.active = SceneHandler(1, [Orc], monster_total_cost=5, loot_drops=0)
SceneHandler.active = MainMenuSceneHandler()
# SceneHandler.active.scene.player.equip(Spear(BASE_SIZE, tier_target=2), 'main_hand')
# SceneHandler.active.scene.player.equip(Swordbreaker(BASE_SIZE, tier_target=2), 'off_hand')


while True:
    SceneHandler.active.execute()
