use std::collections::{HashMap, HashSet};

/// ⚡ Int-ID pipeline: accepts ``HashMap<usize, HashMap<i32, f32>>``,
/// returns the set of bone IDs (i32) that have visible influence.
pub fn get_visible_influence_bones(
    layer_dict: HashMap<usize, HashMap<i32, f32>>,
) -> HashSet<i32> {
    let mut influenced_bones = HashSet::new();
    for weights in layer_dict.values() {
        for (&bone_id, &weight) in weights {
            if weight > 0.001 {
                influenced_bones.insert(bone_id);
            }
        }
    }
    influenced_bones
}
