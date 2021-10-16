# todo:
#  basic menu, starting equipment choice dialogue
#  placeholder background music (e.g. crystal by m.o.o.n.)
# After tech demo
# todo:
#  make ALL string constants come from language json
#  seeded random
#  Sound system
#  Speedrun mode
#  split threads by Input+calculation // drawing OR try to draw less often after splitting input from drawing
#  try to update FPS_TICK by get_time
from scenario import *

print(frame_text([" FENCI: ASCII Game about fencing, looting and dying. A lot. "]))
print("Actually, mostly about dying. A whole lot.\n")

print(f"Droppable weapons: {', '.join(Wielded.registry.keys())or 'None'}")
print(f"Droppable hats: {', '.join(Hat.registry.keys()) or 'None'}")
for tier in range(5):
    level = filter(lambda x: artifacts[x]["tier"] == tier, list(artifacts.keys()))
    print(f"Loaded artifacts at tier {tier}: {', '.join(level) or 'None'}")

sh = SceneHandler(1, [Goblin, Orc], [5, 1])
# sh = SceneHandler(1, [DebugOrc], on_scren_enemies_value=[1, 1], loot_drops=20)
sh.player.equip(Axe(BASE_SIZE, tier_target=2), 'main_hand')
sh.player.equip(Shield(BASE_SIZE, tier_target=2), 'off_hand')
# sh.player.equip(Katar(BASE_SIZE, tier_target=2), 'backpack')
sh.scene.log_weapons()


while True:
    sh.execute()
