bl_info = {
    "name": "BoneCT",
    "author": "空想幻灵",
    "version": (1, 1, 5),  # 更新版本号
    "blender": (2, 83, 0),
    "location": "View 3D > Tool Shelf > BoneCT",
    "description": "Transfer IK controllers and create missing control bones from one MMD armature to another.",
    "category": "Armature",
    "update_date": "2024/12/9"  # 更新日期
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

def create_missing_bones(target_armature, bone_structure, ik_end_bones=None):
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
                        
                        # 如果是IK链末端骨骼，创建target bone并设置其头部位置为IK骨骼的尾部
                        if ik_end_bones and bone_name in ik_end_bones:
                            ik_bone = edit_bones[bone_name]
                            new_bone.head = ik_bone.tail.copy()
                            new_bone.tail = new_bone.head + Vector((0.05, 0, 0))  # 设置默认长度和方向
                            
                            # 创建IK目标骨骼
                            ik_target_name = f"{bone_name}_IK_Target"
                            if ik_target_name not in edit_bones:
                                ik_target_bone = edit_bones.new(ik_target_name)
                                ik_target_bone.head = ik_bone.tail.copy()
                                ik_target_bone.tail = ik_target_bone.head + Vector((0.1, 0, 0))  # 设置默认长度和方向
                                created_bones.append(ik_target_bone.name)
                        else:
                            new_bone.head = bone_data['head']
                            new_bone.tail = bone_data['tail']
                        
                        new_bone.roll = bone_data['roll']
                        
                        if bone_data['parent'] and bone_data['parent'] in edit_bones:
                            new_bone.parent = edit_bones[bone_data['parent']]
                        
                        created_bones.append(new_bone.name)
                
                bpy.ops.object.mode_set(mode=current_mode)
                print(f"Created bones: {created_bones}")  # 输出创建的骨骼列表
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
            print(f"IK Chain End Bones: {ik_chain_ends}")  # 输出IK链末端骨骼
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
                    for attr in ['chain_count', 'use_stretch', 'iterations', 'pole_angle']:
                        if attr in constraint_data:
                            try:
                                setattr(new_constraint, attr, constraint_data[attr])
                            except AttributeError:
                                print(f"Warning: Could not set attribute '{attr}' on IK constraint.")
                    if 'pole_target' in constraint_data:
                        pole_value = constraint_data['pole_target']
                        if pole_value:
                            pole_obj = bpy.data.objects.get(pole_value)
                            if pole_obj and pole_obj.type == 'ARMATURE':
                                setattr(new_constraint, 'pole_target', pole_obj)  # IK极向目标可以是其他骨架
                            else:
                                print(f"Warning: Pole target '{pole_value}' not found or not an armature.")
                                setattr(new_constraint, 'pole_target', None)
                        else:
                            setattr(new_constraint, 'pole_target', None)
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
    
    print(f"Bone Mapping: {bone_mapping}")  # 输出骨骼映射
    return bone_mapping

# 辅助函数：获取IK链中的所有骨骼
def get_ik_chain_bones_recursive(armature):
    """获取IK链中的所有骨骼及其父骨骼"""
    ik_chain_bones = set()
    
    for bone in armature.pose.bones:
        for constraint in bone.constraints:
            if constraint.type == 'IK':
                ik_chain_bones.add(bone.name)
                # 添加IK目标骨骼
                if constraint.subtarget:
                    ik_chain_bones.add(constraint.subtarget)
                # 添加极向目标骨骼
                if constraint.pole_target and constraint.pole_subtarget:
                    ik_chain_bones.add(constraint.pole_subtarget)
    
    # 递归添加所有父骨骼
    pose_bones = armature.pose.bones
    for bone_name in list(ik_chain_bones):
        pb = pose_bones[bone_name]
        while pb.parent:
            ik_chain_bones.add(pb.parent.name)
            pb = pb.parent
    
    print(f"Recursive IK Chain Bones: {ik_chain_bones}")  # 输出递归查找的IK链骨骼
    return ik_chain_bones

class OBJECT_OT_TransferConstraintsOperator(bpy.types.Operator):
    bl_idname = "object.transfer_constraints"
    bl_label = "Transfer Constraints"

    @classmethod
    def poll(cls, context):
        return context.scene.Reference_Armature and context.scene.Armature_to_Add_Constraints

    def execute(self, context):
        reference_armature = context.scene.Reference_Armature
        target_armature = context.scene.Armature_to_Add_Constraints
        
        if not reference_armature or not target_armature:
            self.report({'ERROR'}, "Please select both Reference and Target Armatures in the BoneCT panel before transferring constraints.")
            return {'CANCELLED'}
        
        try:
            # 获取源骨架的骨结构
            try:
                source_bone_structure = get_source_bone_structure(reference_armature)
                print(f"Source Bone Structure: {list(source_bone_structure.keys())}")  # 输出源骨架的骨骼结构
            except Exception as e:
                self.report({'ERROR'}, f"Failed to get source bone structure: {str(e)}")
                return {'CANCELLED'}

            # 查找IK链末端骨骼
            try:
                ik_end_bones = find_ik_chain_end_bones(reference_armature)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to find IK chain end bones: {str(e)}")
                return {'CANCELLED'}

            # 获取IK链中的所有骨骼
            try:
                ik_chain_bones = get_ik_chain_bones_recursive(reference_armature)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to get IK chain bones: {str(e)}")
                return {'CANCELLED'}

            # 分离IK链骨骼和其他骨骼
            ik_bone_structure = {bone_name: bone_data for bone_name, bone_data in source_bone_structure.items() if bone_name in ik_chain_bones}
            other_bone_structure = {bone_name: bone_data for bone_name, bone_data in source_bone_structure.items() if bone_name not in ik_chain_bones}

            print(f"IK Bone Structure: {list(ik_bone_structure.keys())}")  # 输出IK骨骼结构
            print(f"Other Bone Structure: {list(other_bone_structure.keys())}")  # 输出其他骨骼结构

            # 创建缺失的骨骼
            created_bones = []
            if context.scene.Transfer_IK_Bones:
                created_bones.extend(create_missing_bones(target_armature, ik_bone_structure, ik_end_bones))

            if context.scene.Transfer_Missing_Bones:
                created_bones.extend(create_missing_bones(target_armature, other_bone_structure))

            # 创建骨骼映射
            bone_mapping = create_bone_mapping(reference_armature, target_armature, created_bones)

            # 获取所有约束信息
            source_constraints = get_all_constraints(reference_armature)

            # 过滤IK链中的约束
            filtered_constraints = {}
            for bone_name, constraints in source_constraints.items():
                if context.scene.Transfer_IK_Bones and bone_name in ik_chain_bones:
                    filtered_constraints[bone_name] = constraints
                elif context.scene.Transfer_Missing_Bones and bone_name not in ik_chain_bones:
                    filtered_constraints[bone_name] = constraints

            print(f"Filtered Constraints: {filtered_constraints.keys()}")  # 输出过滤后的约束

            # 应用约束到目标骨架
            apply_constraints(target_armature, filtered_constraints, bone_mapping)
            self.report({'INFO'}, "Constraints transferred successfully.")
        except Exception as e:
            self.report({'ERROR'}, f"An unexpected error occurred: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}

class BoneCTPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.label(text=f"Version: {bl_info['version'][0]}.{bl_info['version'][1]}.{bl_info['version'][2]}")
        row = layout.row()
        row.label(text=f"Last Updated: {bl_info['update_date']}")
        row = layout.row()
        row.operator("wm.url_open", text="Visit Repository").url = "https://gitee.com/uitcis/BoneCT"

class VIEW3D_PT_TransferConstraintsPanel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "BoneCT"
    bl_category = "BoneCT"

    def draw(self, context):
        layout = self.layout
        
        col = layout.column()
        col.prop(context.scene, "Reference_Armature", text="Reference Armature")
        col.prop(context.scene, "Armature_to_Add_Constraints", text="Armature to Add Constraints")
        
        col.separator()
        
        col.prop(context.scene, "Transfer_IK_Bones", text="Transfer IK Bones and Constraints")
        col.prop(context.scene, "Transfer_Missing_Bones", text="Transfer Other Missing Bones and Constraints")
        
        # 检查是否选择了目标骨骼
        reference_armature = context.scene.Reference_Armature
        target_armature = context.scene.Armature_to_Add_Constraints
        
        if reference_armature and target_armature:
            col.operator("object.transfer_constraints", text="Transfer Constraints")
        else:
            col.operator("object.transfer_constraints", text="Transfer Constraints", icon='LOCKED').enabled = False

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
    bpy.types.Scene.Transfer_IK_Bones = bpy.props.BoolProperty(
        name="Transfer IK Bones and Constraints",
        description="Transfer IK bones and their constraints",
        default=True
    )
    bpy.types.Scene.Transfer_Missing_Bones = bpy.props.BoolProperty(
        name="Transfer Other Missing Bones and Constraints",
        description="Transfer other missing bones and their constraints",
        default=False
    )

classes = (
    OBJECT_OT_TransferConstraintsOperator,
    BoneCTPreferences,
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
    del bpy.types.Scene.Transfer_IK_Bones
    del bpy.types.Scene.Transfer_Missing_Bones

if __name__ == "__main__":
    register()


