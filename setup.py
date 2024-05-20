import setuptools

setuptools.setup(
    name="redfid_edx_user_manager",
    version="0.0.1",
    author="Vicente Daie",
    author_email="vdaiep@gmail.com",
    description=".",
    url="https://www.redfid.cl",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 2",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "lms.djangoapp": ["redfid_edx_user_manager = redfid_edx_user_manager.apps:RedfidEdxUserManager"],
        "cms.djangoapp": ["redfid_edx_user_manager = redfid_edx_user_manager.apps:RedfidEdxUserManager"]
    },
)