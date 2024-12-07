bl_info = {
    "name": "BoneCT",
    "author": "空想幻灵",
    "version": (1, 0, 9),
    "blender": (2, 83, 0),
    "location": "View 3D > Tool Shelf > BoneCT ",
    "description": "Transfer IK controllers and create missing control bones from one MMD armature to another.",
    "warning": "2024/12/5版",
    "wiki_url": "https://gitee.com/uitcis/",
    "category": "Armature",
}

import bpy
from mathutils import Vector

def get_source_bone_structure(source_armature):
    bone_structure = {}
    if source_armature:
        current_mode = bpy.context.object.mode
        try:
            bpy.context.view_layer.objects.active = source_armature
            if bpy.ops.object.mode_set.poll():
                bpy.ops.object.mode_set(mode='EDIT')
                
                edit_bones = source_armature.data.edit_bones
                
                for bone in edit_bones:
                    parent_name = bone.parent.name if bone.parent else None
                    bone_structure[bone.name] = {
                        'head': bone.head.copy(),
                        'tail': bone.tail.copy(),
                        'roll': bone.roll,
                        'parent': parent_name,
                    }
                
                bpy.ops.object.mode_set(mode=current_mode)
            else:
                raise RuntimeError("Cannot switch to EDIT mode.")
        except Exception as e:
            bpy.ops.object.mode_set(mode=current_mode)
            raise RuntimeError(f"Failed to get source bone structure: {e}")
    return bone_structure

def create_missing_bones(target_armature, bone_structure, ik_end_bone=None):
    current_mode = bpy.context.object.mode
    try:
        if target_armature:
            bpy.context.view_layer.objects.active = target_armature
            if bpy.ops.object.mode_set.poll():
                bpy.ops.object.mode_set(mode='EDIT')
                
                edit_bones = target_armature.data.edit_bones
                
                created_bones = []
                for bone_name, bone_data in bone_structure.items():
                    if bone_name not in edit_bones:
                        new_bone = edit_bones.new(bone_name)
                        new_bone.head = bone_data['head']
                        new_bone.tail = bone_data['tail']
                        new_bone.roll = bone_data['roll']
                        
                        if bone_data['parent'] and bone_data['parent'] in edit_bones:
                            new_bone.parent = edit_bones[bone_data['parent']]
                        
                        # 如果是IK chain end bone，创建target bone并设置其头部位置为IK骨骼的尾部
                        if ik_end_bone and bone_name == ik_end_bone:
                            new_bone.head = edit_bones[ik_end_bone].tail.copy()
                            new_bone.tail = new_bone.head + Vector((0.05, 0, 0))  # 设置默认长度和方向
                        
                        created_bones.append(new_bone.name)
                
                bpy.ops.object.mode_set(mode=current_mode)
                return created_bones
            else:
                raise RuntimeError("Cannot switch to EDIT mode.")
        else:
            raise RuntimeError("Target armature is not available.")
    except Exception as e:
        bpy.ops.object.mode_set(mode=current_mode)
        raise RuntimeError(f"Failed to create missing bones: {e}")

def find_ik_chain_end_bones(armature):
    """查找包含IK约束的骨骼，并返回所有链末端骨骼的名称"""
    current_mode = bpy.context.object.mode if bpy.context.object else 'OBJECT'
    try:
        bpy.context.view_layer.objects.active = armature
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='POSE')
            
            pose_bones = armature.pose.bones
            ik_chain_ends = []

            for pb in pose_bones:
                for c in pb.constraints:
                    if c.type == 'IK':
                        ik_chain_ends.append(pb.name)
                        break  # 每个骨骼只记录一次
            
            bpy.ops.object.mode_set(mode=current_mode)
            return ik_chain_ends
        else:
            raise RuntimeError("Cannot switch to POSE mode.")
    except Exception as e:
        bpy.ops.object.mode_set(mode=current_mode)
        raise RuntimeError(f"Failed to find IK chain end bones: {e}")

def get_all_constraints(armature):
    all_constraints = {}
    for bone in armature.pose.bones:
        bone_constraints = []
        for constraint in bone.constraints:
            constraint_data = {}
            for attr in dir(constraint):
                if not attr.startswith("_") and not callable(getattr(constraint, attr)):
                    try:
                        value = getattr(constraint, attr)
                        constraint_data[attr] = value
                    except AttributeError:
                        pass  # 忽略无法获取的属性
            bone_constraints.append(constraint_data)
        if bone_constraints:
            all_constraints[bone.name] = bone_constraints
    return all_constraints

def apply_constraints(target_armature, source_constraints, bone_mapping):
    current_mode = bpy.context.object.mode if bpy.context.object else 'OBJECT'
    
    try:
        if not target_armature or not isinstance(target_armature, bpy.types.Object) or target_armature.type != 'ARMATURE':
            raise RuntimeError("Target armature is not available or not an armature.")
        
        bpy.context.view_layer.objects.active = target_armature
        if bpy.ops.object.mode_set.poll() and current_mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')
        
        pose_bones = target_armature.pose.bones
        
        for source_bone_name, constraints in source_constraints.items():
            if source_bone_name not in pose_bones:
                print(f"Warning: Bone '{source_bone_name}' does not exist in the target armature.")
                continue
            
            pb = pose_bones[source_bone_name]
            
            for constraint_data in constraints:
                c_type = constraint_data.get('type', '')
                new_constraint = pb.constraints.new(c_type)
                
                # 设置除 'type' 外的所有其他属性
                for attr, value in constraint_data.items():
                    if hasattr(new_constraint, attr) and attr != 'type':  # 跳过 'type'
                        if attr == 'target':
                            # 确保约束的目标总是当前的目标骨架对象
                            setattr(new_constraint, attr, target_armature)
                        elif attr == 'subtarget' and isinstance(value, str):
                            # 使用映射来找到对应的目标骨骼
                            mapped_subtarget = bone_mapping.get(value)
                            if mapped_subtarget and mapped_subtarget in pose_bones:
                                setattr(new_constraint, attr, mapped_subtarget)
                            else:
                                print(f"Warning: Subtarget bone '{value}' not found in the target armature.")
                        elif attr in {'target_space', 'owner_space'} and isinstance(value, str):
                            # 尝试将字符串转换为有效的枚举值
                            enum_values = [item.identifier for item in new_constraint.rna_type.properties[attr].enum_items]
                            if value.upper() in enum_values:
                                setattr(new_constraint, attr, value.upper())
                            else:
                                print(f"Warning: Invalid space setting '{value}' for attribute '{attr}'. Using default.")
                        else:
                            try:
                                setattr(new_constraint, attr, value)
                            except AttributeError:
                                print(f"Warning: Could not set attribute '{attr}' on constraint of type '{c_type}'.")
                # 特殊处理特定类型的约束
                if c_type == 'IK':
                    for attr in ['chain_count', 'use_stretch', 'iterations', 'pole_target', 'pole_angle']:
                        if attr in constraint_data:
                            if attr == 'pole_target':
                                pole_value = constraint_data[attr]
                                if pole_value and pole_value in bpy.data.objects:
                                    pole_obj = bpy.data.objects[pole_value]
                                    if pole_obj.type == 'ARMATURE':
                                        setattr(new_constraint, attr, pole_obj)  # IK极向目标可以是其他骨架
                                    else:
                                        print(f"Warning: Pole target '{pole_value}' not found or not an armature.")
                                        setattr(new_constraint, attr, None)
                                else:
                                    setattr(new_constraint, attr, None)
                            else:
                                try:
                                    setattr(new_constraint, attr, constraint_data[attr])
                                except AttributeError:
                                    print(f"Warning: Could not set attribute '{attr}' on IK constraint.")
                elif c_type == 'DAMPED_TRACK':
                    for attr in ['track_axis', 'influence']:
                        if attr in constraint_data:
                            try:
                                setattr(new_constraint, attr, constraint_data[attr])
                            except AttributeError:
                                print(f"Warning: Could not set attribute '{attr}' on DAMPED_TRACK constraint.")
                elif c_type in ['COPY_LOCATION', 'COPY_ROTATION', 'COPY_SCALE']:
                    for attr in ['use_offset', 'invert_x', 'invert_y', 'invert_z', 'use_x', 'use_y', 'use_z', 'mix_mode', 'owner_space', 'target_space']:
                        if attr in constraint_data:
                            try:
                                setattr(new_constraint, attr, constraint_data[attr])
                            except AttributeError:
                                print(f"Warning: Could not set attribute '{attr}' on {c_type} constraint.")
                elif c_type == 'LIMIT_ROTATION':
                    for attr in ['use_limit_x', 'use_limit_y', 'use_limit_z', 'min_x', 'max_x', 'min_y', 'max_y', 'min_z', 'max_z', 'owner_space']:
                        if attr in constraint_data:
                            try:
                                setattr(new_constraint, attr, constraint_data[attr])
                            except AttributeError:
                                print(f"Warning: Could not set attribute '{attr}' on LIMIT_ROTATION constraint.")

        if current_mode != 'POSE':
            bpy.ops.object.mode_set(mode=current_mode)
    
    except Exception as e:
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode=current_mode)
        raise RuntimeError(f"Failed to apply constraints: {e}")

# 辅助函数：创建从源骨架到目标骨架的骨骼名称映射
def create_bone_mapping(source_armature, target_armature, created_bones=[]):
    """创建从源骨架到目标骨架的骨骼名称映射"""
    source_bones = [bone.name for bone in source_armature.pose.bones]
    target_bones = [bone.name for bone in target_armature.pose.bones]

    bone_mapping = {}
    for source_name in source_bones:
        if source_name in target_bones:
            bone_mapping[source_name] = source_name  # 假设骨骼名称一致
        elif source_name in created_bones:
            bone_mapping[source_name] = source_name  # 已经创建的骨骼
        else:
            print(f"Warning: Bone '{source_name}' not found in the target armature.")
    
    return bone_mapping

class OBJECT_OT_TransferConstraintsOperator(bpy.types.Operator):
    bl_idname = "object.transfer_constraints"
    bl_label = "Transfer Constraints"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'ARMATURE'

    def execute(self, context):
        reference_armature = context.scene.Reference_Armature
        target_armature = context.scene.Armature_to_Add_Constraints
        
        if not reference_armature or not target_armature:
            self.report({'ERROR'}, "Please select both Reference and Target Armatures in the BoneCT panel before transferring constraints.")
            return {'CANCELLED'}
        
        try:
            # 获取源骨架的骨结构
            source_bone_structure = get_source_bone_structure(reference_armature)
            
            # 创建缺失的骨骼
            created_bones = create_missing_bones(target_armature, source_bone_structure)
            
            # 创建骨骼映射
            bone_mapping = create_bone_mapping(reference_armature, target_armature, created_bones)
            
            # 获取所有约束信息
            source_constraints = get_all_constraints(reference_armature)
            # 应用约束到目标骨架
            apply_constraints(target_armature, source_constraints, bone_mapping)
            self.report({'INFO'}, "Constraints transferred successfully.")
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        
        return {'FINISHED'}

class VIEW3D_PT_TransferConstraintsPanel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Transfer Constraints"
    bl_category = "BoneCT"

    def draw(self, context):
        layout = self.layout
        
        col = layout.column()
        col.prop(context.scene, "Reference_Armature", text="Reference Armature")
        col.prop(context.scene, "Armature_to_Add_Constraints", text="Armature to Add Constraints")
        col.operator("object.transfer_constraints", text="Transfer Constraints")

def register_enum_properties():
    bpy.types.Scene.Reference_Armature = bpy.props.PointerProperty(
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
        name="Reference Armature",
        description="The armature used as a reference for bone structure and constraints"
    )
    bpy.types.Scene.Armature_to_Add_Constraints = bpy.props.PointerProperty(
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE',
        name="Armature to Add Constraints",
        description="The armature where constraints will be added"
    )

classes = (
    OBJECT_OT_TransferConstraintsOperator,
    VIEW3D_PT_TransferConstraintsPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_enum_properties()

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.Reference_Armature
    del bpy.types.Scene.Armature_to_Add_Constraints

if __name__ == "__main__":
    register()



