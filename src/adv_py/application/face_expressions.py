"""Original facial expression stages; each includes its predecessor Finish."""

EXPRESSION_STAGES={
    "blink":"fit_original_face_eye_blink","blink_finish":"finish_original_face_eye_blink",
    "wide":"fit_original_face_eye_wide","wide_finish":"finish_original_face_eye_wide",
    "squint":"fit_original_face_squint","squint_finish":"finish_original_face_squint",
    "smile":"fit_original_face_smile_pull","smile_finish":"finish_original_face_smile_pull",
    "frown":"fit_original_face_frown_pull","frown_finish":"finish_original_face_frown_pull",
    "cheek":"fit_original_face_cheek","cheek_finish":"finish_original_face_cheek",
    "cheek_raiser":"fit_original_face_cheek_raiser","cheek_raiser_finish":"finish_original_face_cheek_raiser",
    "snarl":"fit_original_face_snarl","snarl_finish":"finish_original_face_snarl",
    "eye_aim":"show_original_face_eye_aim","up_mid_lo":"create_original_face_up_mid_lo",
    "phonemes":"create_original_face_phonemes","emotions":"create_original_face_emotions",
    "extra_drivers":"create_original_face_extra_drivers","extras":"transfer_original_face_extras",
    "finish":"finish_original_face"}

class FitFaceExpression:
    def __init__(self,host): self.host=host
    def apply(self,stage):
        if stage not in EXPRESSION_STAGES: raise ValueError("未知 Face 表情阶段："+stage)
        source=self.host.capture_face_cage_input() if stage in ("smile","snarl","up_mid_lo") else None
        if stage in ("smile","snarl","up_mid_lo") and source is None: return None
        if stage=="finish": source=self.host.preflight_original_face_finish()
        with self.host.transaction("Face 表情修形："+stage):
            before=self.host.capture_face_build_node_ids()
            method=getattr(self.host,EXPRESSION_STAGES[stage])
            result=method(source) if stage in ("smile","snarl","up_mid_lo","finish") else method()
            if result:
                # Narrow Smile/Frown introduces the two visible SmilePull
                # controls; retain their neutral pose before later Face stages.
                if stage=="frown_finish": self.host.extend_face_build_pose(("SmilePull_R","SmilePull_L"))
                skins=result.get("production_skins",()) if isinstance(result,dict) else ()
                if stage=="extras": skins=result
                if stage=="extra_drivers": self.host.extend_face_build_pose(result)
                if isinstance(result,dict) and result.get("controls"): self.host.extend_face_build_pose(result["controls"])
                if stage!="finish": self.host.register_face_module_nodes(before,"FaceExpressionSet",reuse=True,production_skins=skins)
            return result
